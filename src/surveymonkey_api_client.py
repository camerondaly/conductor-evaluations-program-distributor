# surveymonkey_client.py
import requests
from datetime import datetime, timezone


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
    def get_survey_id_by_name(self, template_name):
        resp = requests.get(f"{self.base_url}/surveys", headers=self.headers)
        resp.raise_for_status()
        for survey in resp.json().get("data", []):
            if template_name.lower() in survey["title"].lower():
                return survey["id"]
        raise ValueError(f"Survey template '{template_name}' not found")

    # ------------------------
    # Collector
    # ------------------------
    def create_collector(self, survey_id, collector_name, page_title=None):
        payload = {"type": "weblink", "name": collector_name}
        resp = requests.post(f"{self.base_url}/surveys/{survey_id}/collectors", headers=self.headers, json=payload)
        resp.raise_for_status()
        collector = resp.json()
        collector_id = collector["id"]
        url = collector.get("url")

        # Optional: set custom page title per conductor
        if page_title:
            patch_payload = {"display_settings": {"survey_title": page_title}}
            patch_resp = requests.patch(f"{self.base_url}/collectors/{collector_id}", headers=self.headers, json=patch_payload)
            patch_resp.raise_for_status()

        return collector_id, url

    def get_collector(self, survey_id, collector_name):
        # TODO: return None if there is no such collector else return it?
        return None
    
    def get_collector_by_name(self, survey_id, collector_name) -> tuple[str, str]:
        """
        Fetch collector ID (and URL) for a given survey by collector name using SM API 'name' filter.
        Returns (collector_id, collector_url) or (None, None) if not found.
        """
        url = f"https://api.surveymonkey.com/v3/surveys/{survey_id}/collectors"
        params = {"name": collector_name}
        
        response = requests.get(url, headers=self.headers, params=params)
        if response.status_code != 200:
            print(f"Warning: failed to fetch collectors (status {response.status_code})")
            return None, None

        data = response.json()
        collectors = data.get("data", [])
        if not collectors:
            return None, None

        # Take first match
        col = collectors[0]
        return col["id"], col.get("href")  # href is collector URL


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
    def send_message(self, collector_id, subject, body, schedule_dt=None, message_type="invite"):
        payload = {"type": message_type, "subject": subject, "body": body}
        if schedule_dt:
            dt_utc = datetime.fromisoformat(schedule_dt).astimezone(timezone.utc)
            payload["schedule"] = {"send_at": dt_utc.isoformat().replace("+00:00", "Z")}
        resp = requests.post(f"{self.base_url}/collectors/{collector_id}/messages", headers=self.headers, json=payload)
        resp.raise_for_status()
        message_id = resp.json()["id"]

        # Send immediately (or schedule)
        send_resp = requests.post(f"{self.base_url}/collectors/{collector_id}/messages/{message_id}/send", headers=self.headers)
        send_resp.raise_for_status()
        return send_resp.json()
