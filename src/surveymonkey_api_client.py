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
        Clone a template survey by ID and name the new copy new_title.
        Returns the new survey_id.
        """
        url = f"{self.base_url}/surveys"
        # TODO: remove test folder ID and replate with automation folder id
        payload = {"title": new_title, "folder_id": "1373789", "from_survey_id": survey_id}
        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    # ------------------------
    # Collector
    # ------------------------
    def create_collector(self, survey_id, collector_name):
        payload = {"type": "email", "name": collector_name}
        print("create collextor payload: ")
        print(payload)
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

        print(f"SM AAPI: trying to get collector by collector name: '{collector_name}'")
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"Warning: failed to fetch collectors (status {response.status_code})")
            return None, None
        data = response.json()

        print("--------- get_collector_by_name response")
        print(data)
        print("---------")

        collectors = data.get("data", [])
        if not collectors:
            return None, None

        print("Found the collector by name.", collectors)

        col = collectors[0]
        return col["id"], col.get("href")

    # ------------------------
    # Recipients
    # ------------------------
    def add_recipients(self, collector_id, message_id, emails):
        formatted_recipients = {"contacts": []}
        for email in emails:
            formatted_recipients["contacts"].append({"email": email})
        if formatted_recipients["contacts"]:
            print("Logging first formattted recipient to add: ", formatted_recipients["contacts"][0])
        resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/recipients/bulk",
            headers=self.headers,
            json=formatted_recipients
        )
        resp.raise_for_status()
        return resp.json()

    def delete_recipients_in_collector_but_not_in_file(self, collector_id, sheet_emails):
        """
        Sync collector recipients to match the current sheet.
        Only remove recipients who are no longer in the sheet.
        Adding new recipients can be done in bulk; duplicates are ignored by SM.
        """
        # Fetch current recipients
        existing = self.get_recipients(collector_id)
        existing_emails = {r["email"]: r["id"] for r in existing}

        # Identify emails to remove
        to_remove = set(existing_emails.keys()) - set(sheet_emails)

        if to_remove:
            print("Collector has emails that are not present in latest file:")
            print(to_remove)
        else:
            print("No recipients exist on the collector that are not present in the file.")

        # Remove recipients no longer in sheet
        for email in to_remove:
            rid = existing_emails[email]
            url = f"{self.base_url}/collectors/{collector_id}/recipients/{rid}"
            response = requests.delete(url, headers=self.headers)
            if response.status_code not in (200, 204):
                print(f"Warning: failed to remove recipient {email} (status {response.status_code})")
        print("Recipient removed from file have been removed from the collector.")

    def get_recipients(self, collector_id):
        """
        Fetch existing recipients for a collector.
        Returns a list of dicts with at least 'id' and 'email'.
        """
        recipients = []
        url = f"https://api.surveymonkey.com/v3/collectors/{collector_id}/recipients"
        while url:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                print(f"Warning: failed to fetch recipients (status {response.status_code})")
                break
            data = response.json()
            recipients.extend(data.get("data", []))
            url = data.get("links", {}).get("next")
        return recipients

    # ------------------------
    # Messages
    # ------------------------
    def schedule_message(self, collector_id, message_id, schedule_dt):
        # Schedule message
        send_payload = {}
        dt_utc = self._parse_iso_z(schedule_dt).astimezone(timezone.utc)
        send_payload["scheduled_date"] = self._to_api_iso_z(dt_utc)

        send_resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/send",
            headers=self.headers,
            json=send_payload
        )
        send_resp.raise_for_status()
        return send_resp.json()
    
    def create_invite_message(self, collector_id, survey_name):
        # Create message and return ID
        subject = survey_name
        payload = {"type": "invite", "subject": subject, "embed_first_question": True}
        resp = requests.post(f"{self.base_url}/collectors/{collector_id}/messages", headers=self.headers, json=payload)
        resp.raise_for_status()
        message_id = resp.json()["id"]
        return message_id
    
    def create_reminder_message(self, collector_id, subject):
        create_payload = {
            "subject": subject,
            "type": "reminder",
            "embed_first_question": True,
            "recipient_status": "has_not_responded"
        }
        # Create reminder message
        resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages",
            headers=self.headers,
            json=create_payload,
        )
        resp.raise_for_status()
        message_id = resp.json()["id"]
        return message_id
    
    def schedule_reminder_message_send(self, collector_id, message_id, invite_sent_dt, days_after=3):
        """
        Schedule a reminder for an email collector for 3 days after collector is sent.
        Only goes to recipients who have not responded or partially responded.
        """
        # Calculate reminder time
        invite_dt = self._parse_iso_z(invite_sent_dt)
        reminder_dt = (invite_dt + timedelta(days=days_after)).astimezone(timezone.utc)
        schedule_payload = {"scheduled_date": self._to_api_iso_z(reminder_dt)}

        # Schedule the reminder
        send_resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/send",
            headers=self.headers,
            json=schedule_payload
        )
        send_resp.raise_for_status()
        return send_resp.json()
    
    def get_messages_on_collector(self, collector_id):
        resp = requests.get(f"{self.base_url}/collectors/{collector_id}/messages", headers=self.headers)
        messages_array = resp.json()["data"]
        return messages_array
    
    # ------------------------
    # Helpers
    # ------------------------

    # Helper: robust ISO parsing that accepts trailing 'Z'
    def _parse_iso_z(self, s: str) -> datetime:
        # Accept strings like '2025-09-16T21:40:00Z' or with offset '+00:00'
        if s is None:
            raise ValueError("None passed to _parse_iso_z")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)

    # Helper: produce SurveyMonkey compatible UTC ISO ending with 'Z'
    def _to_api_iso_z(self, dt: datetime) -> str:
        if dt.tzinfo is None:
            # assume naive datetimes are in UTC; adjust if you use local time
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.isoformat().replace("+00:00", "Z")
