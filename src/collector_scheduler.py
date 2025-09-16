# distributor.py
from google_sheets_api_client import GoogleSheetsApiClient
from surveymonkey_api_client import SurveyMonkeyApiClient
from src.config import SURVEYMONKEY_API_TOKEN, SURVEY_TEMPLATES, DEFAULT_SUBJECT, DEFAULT_BODY


class CollectorScheduler:
    def __init__(self, event_type, sheet_id, worksheet_name="Sheet1"):
        self.event_type = event_type
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        self.surveymonkey_client = SurveyMonkeyApiClient(SURVEYMONKEY_API_TOKEN)
        self.google_sheets_client = GoogleSheetsApiClient()
        self.survey_template = SURVEY_TEMPLATES[event_type]

    def run(self):
        # Pull data from sheet
        event_title, conductor_name, event_date, recipients = self.google_sheets_client.read_roster_sheet(self.sheet_id, self.worksheet_name)
        if not recipients:
            print(f"No recipients found for {event_title}, skipping.")
            return

        # Collector + page title
        collector_name = f"{conductor_name} - {event_date}"
        page_title = f"Conductor Evaluation: {conductor_name} ({event_date})"

        # Get survey ID
        survey_id = self.surveymonkey_client.get_survey_id_by_name(self.survey_template)

        # Create collector
        if self.does_collector_with_this_name_already_exist(collector_name):
            print("This concert cycle already has a collector created.")
            return
        collector_id, collector_url = self.surveymonkey_client.create_collector(survey_id, collector_name, page_title)

        # Add recipients
        self.surveymonkey_client.add_recipients(collector_id, recipients)

        # Send the survey
        self.surveymonkey_client.send_message(collector_id, DEFAULT_SUBJECT.format(title=event_title),
                                 DEFAULT_BODY.format(title=event_title), schedule_dt=event_date)

        print(f"Sent survey for {conductor_name}. Collector URL: {collector_url}")

    def does_collector_with_this_name_already_exist(self, collector_name: str):
        collector = self.surveymonkey_client.get_collector(collector_name)
        if collector:
            return True
        else:
            return False
