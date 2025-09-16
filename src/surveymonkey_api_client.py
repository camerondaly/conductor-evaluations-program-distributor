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

    # ------------------------
    # Recipients
    # ------------------------
    def add_recipients(self, collector_id, emails):
        recipients = [{"email": e} for e in emails]
        resp = requests.post(
            f"{self.base_url}/collectors/{collector_id}/recipients/bulk",
            headers=self.headers,
            json={"recipients": recipients}
        )
        resp.raise_for_status()
        return resp.json()

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
