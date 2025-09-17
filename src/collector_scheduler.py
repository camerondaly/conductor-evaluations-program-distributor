from datetime import datetime, timedelta
from google_sheets_api_client import GoogleSheetsApiClient
from surveymonkey_api_client import SurveyMonkeyApiClient
from config import SURVEY_TEMPLATES, DEFAULT_SUBJECT, DEFAULT_BODY, UNPROCESSED_FOLDER_ID, PROCESSED_FOLDER_ID
from config_local import SURVEYMONKEY_API_TOKEN

class CollectorScheduler:
    def __init__(self):
        self.surveymonkey_client = SurveyMonkeyApiClient(SURVEYMONKEY_API_TOKEN)
        self.google_sheets_client = GoogleSheetsApiClient()

    def run(self):
        # Get all unprocessed sheets
        sheets = self.google_sheets_client.list_sheets_in_folder(UNPROCESSED_FOLDER_ID)
        for sheet_id, sheet_name in sheets:
            # Pull data from sheet
            event_title, conductor_name, event_date, recipient_emails_on_sheet = self.google_sheets_client.read_roster_sheet(self.sheet_id)
            if not recipient_emails_on_sheet:
                print(f"No recipients found for {event_title}, skipping.")
                return

            # create Collector name and page title
            collector_name = f"Email Invitation for {conductor_name} ({event_title})"  # e.g., Ludovic Morlot (SUB 9)
            page_title = f"Conductor Evaluation for {collector_name}"

            # Get survey ID
            required_survey_template = self.disambiguate_survey_type(event_title)
            survey_id = self.surveymonkey_client.get_survey_id_by_name(SURVEY_TEMPLATES[required_survey_template])

            # Handle case where collector exists and we need to sync the recipient list. Else, create it.
            if self.does_collector_with_this_name_already_exist(survey_id, collector_name):
                print("This exists already. Adding/removing recipients...")
                self.surveymonkey_client.sync_recipients(recipient_emails_on_sheet)
                print("Recipients on collector synced with file.")
            else:
                collector_id, collector_url = self.surveymonkey_client.create_collector(
                    survey_id, collector_name, page_title
                )
                # Add recipients
                self.surveymonkey_client.add_recipients(collector_id, recipient_emails_on_sheet)

            # Send the survey
            self.surveymonkey_client.send_message(collector_id, DEFAULT_SUBJECT.format(title=page_title),
                                    DEFAULT_BODY.format(title=page_title), schedule_dt=self.get_distribution_time_for_event_date(event_date))

            print(f"Sent survey for {conductor_name}. Collector URL: {collector_url}. Moving to processed folder.")

            # Move sheet to processed folder
            self.google_sheets_client.move_sheet_to_folder(sheet_id, PROCESSED_FOLDER_ID)

            print(f"{sheet_name} moved to processed.")

    def does_collector_with_this_name_already_exist(self, survey_id: str, collector_name: str):
        collector_id, collector_url = self.surveymonkey_client.get_collector_by_name(survey_id, collector_name)
        if collector_id and collector_url:
            print("A collector for this conductor+program already exists.")
            return True
        else:
            return False

    def get_distribution_time_for_event_date(self, event_date_str):
        """
        Given last concert time as string (e.g., '2025-09-16 20:00'),
        returns a timestamp 100 minutes later in ISO 8601 format
        suitable for SurveyMonkey API scheduling.
        """
        # Parse the input string
        event_dt = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M")
        # Add 100 minutes
        distribution_dt = event_dt + timedelta(minutes=100)
        # Return ISO 8601 string (SurveyMonkey usually expects UTC)
        return distribution_dt.isoformat() + "Z"  # append 'Z' if using UTC
    
    def disambiguate_survey_type(self, event_title: str):
        # TODO polish this
        event_title_lowercacse = event_title.lower()
        if event_title_lowercacse.contains("opera"):
            return "Seattle Opera"
        return "SSO"
