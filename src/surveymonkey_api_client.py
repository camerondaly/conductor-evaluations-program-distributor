# surveymonkey_client.py
import requests
from datetime import datetime, timezone, timedelta


class SurveyMonkeyApiClient:
    def __init__(self, api_token):
        self.api_token = api_token
        self.base_url = "https://api.surveymonkey.com/v3"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

    # ------------------------
    # Survey
    # ------------------------
    def get_survey_id_by_name(self, survey_name):
        params = {"title": survey_name}
        resp = requests.get(f"{self.base_url}/surveys", headers=self.headers, params=params)
        if resp.status_code != 200:
            print(f"Warning: failed to fetch surveys (status {resp.status_code})")
            return None, None

        data = resp.json().get("data", [])
        if not data:
            return None, None

        survey = data[0]
        return survey["id"], survey["title"]
    
    def clone_survey(self, survey_id, new_title):
        """
        Clone a survey by ID with a new title.
        Returns the new survey_id.
        """
        url = f"{self.base_url}/surveys/{survey_id}/copy"
        # TODO: remove test folder ID and replate with automation folder id
        payload = {"title": new_title, "folder_id": "1373789"}
        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    # def update_question_text(self, survey_id, page_id, question_id, new_text):
    #     """
    #     Replace a question's heading text.
    #     """
    #     url = f"{self.base_url}/surveys/{survey_id}/pages/{page_id}/questions/{question_id}"
    #     payload = {"headings": [{"heading": new_text}]}
    #     resp = requests.patch(url, headers=self.headers, json=payload)
    #     resp.raise_for_status()
    #     return resp.json()

    # ------------------------
    # Collector
    # ------------------------
    def create_collector(self, survey_id, collector_name, close_timestamp):
        payload = {"type": "email", "name": collector_name, "close_date": close_timestamp}
        resp = requests.post(f"{self.base_url}/surveys/{survey_id}/collectors", headers=self.headers, json=payload)
        resp.raise_for_status()
        collector = resp.json()
        collector_id = collector["id"]
        url = collector.get("url")

        return collector_id, url

    def get_collector_by_name(self, survey_id, collector_name) -> tuple[str, str]:
        """
        Fetch collector ID (and URL) for a given survey by collector name.
        Returns (collector_id, collector_url) or (None, None) if not found.
        """
        url = f"{self.base_url}/surveys/{survey_id}/collectors"
        params = {"name": collector_name}
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"Warning: failed to fetch collectors (status {response.status_code})")
            return None, None

        data = response.json()
        collectors = data.get("data", [])
        if not collectors:
            return None, None

        col = collectors[0]
        return col["id"], col.get("url")
    
    def schedule_reminder_after_collector(self, collector_id, subject, body, invite_sent_dt, days_after=3):
        """
        Schedule a reminder for an email collector for 3 days after collector is sent.
        Only goes to recipients who have not responded or partially responded.
        """
        # Calculate reminder time
        invite_dt = datetime.fromisoformat(invite_sent_dt)
        reminder_dt = (invite_dt + timedelta(days=days_after)).astimezone(timezone.utc)
        payload = {
            "type": "reminder",
            "subject": subject,
            "body": body,
            "recipients": {
                "criteria_status": ["not_responded", "partially_responded"]
            }
        }
        # Create reminder message
        resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages",
            headers=self.headers,
            json=payload,
        )
        resp.raise_for_status()
        message_id = resp.json()["id"]
        # Schedule the reminder
        schedule_payload = {"scheduled_date": reminder_dt}
        send_resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/send",
            headers=self.headers,
            json=schedule_payload
        )
        send_resp.raise_for_status()
        return send_resp.json()


    # ------------------------
    # Recipients
    # ------------------------
    def add_recipients(self, collector_id, emails):
        recipients = [{"email": e} for e in emails]
        resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/recipients",
            headers=self.headers,
            json={"recipients": recipients}
        )
        resp.raise_for_status()
        return resp.json()

    def sync_recipients(self, collector_id, emails):
        """
        Sync collector recipients to match the current sheet.
        Only remove recipients who are no longer in the sheet.
        Adding new recipients can be done in bulk; duplicates are ignored by SM.
        """
        # Fetch current recipients
        existing = self.get_recipients(collector_id)
        existing_emails = {r["email"]: r["id"] for r in existing}

        # Identify emails to remove
        to_remove = set(existing_emails.keys()) - set(emails)

        # Remove recipients no longer in sheet
        for email in to_remove:
            rid = existing_emails[email]
            url = f"https://api.surveymonkey.com/v3/collectors/{collector_id}/recipients/{rid}"
            response = requests.delete(url, headers=self.headers)
            if response.status_code not in (200, 204):
                print(f"Warning: failed to remove recipient {email} (status {response.status_code})")

    def get_recipients(self, collector_id):
        """
        Fetch existing recipients for a collector.
        Returns a list of dicts with at least 'id' and 'email'.
        """
        recipients = []
        url = f"https://api.surveymonkey.com/v3/collectors/{collector_id}/recipients"
        page = 1
        while url:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                print(f"Warning: failed to fetch recipients (status {response.status_code})")
                break
            data = response.json()
            recipients.extend(data.get("data", []))
            url = data.get("links", {}).get("next")
            page += 1
        return recipients

    # ------------------------
    # Send message
    # ------------------------
    def send_message(self, collector_id, survey_name, schedule_dt):
        # Create message
        subject = survey_name
        body = f"Please complete your {survey_name}. Thank you!"
        payload = {"type": "invite", "subject": subject, "body": body}
        resp = requests.post(f"{self.base_url}/collectors/{collector_id}/messages", headers=self.headers, json=payload)
        resp.raise_for_status()
        message_id = resp.json()["id"]

        # Schedule message
        send_payload = {}
        dt_utc = datetime.fromisoformat(schedule_dt).astimezone(timezone.utc)
        send_payload["scheduled_date"] = dt_utc.isoformat().replace("+00:00", "Z")

        send_resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/send",
            headers=self.headers,
            json=send_payload
        )
        send_resp.raise_for_status()
        return send_resp.json()
