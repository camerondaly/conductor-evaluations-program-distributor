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
            event_title, conductor_name, event_date, recipient_emails_on_sheet = self.google_sheets_client.read_roster_sheet(sheet_id)
            if not recipient_emails_on_sheet:
                print(f"No recipients found for {event_title}, skipping.")
                return

            # create Collector name and page title and Survey Name
            collector_name = f"Email Invitation for {conductor_name} ({event_title})"  # e.g., Ludovic Morlot (SUB 9)
            survey_name = f"Conductor Evaluation for {conductor_name} ({event_title})"

            # Get appropariate template Survey ID
            template_survey_id = self.get_required_template_survey_id(event_title)


            print("event_title, conductor_name, event_date, recipient_emails_on_sheet:")
            print(event_title, conductor_name, event_date, recipient_emails_on_sheet)
            print("^ thats from g drive")


            # Create survey w this name if does not exist. Proceed to collector creation/update if survey exists.
            existing_survey_id, existing_title = self.surveymonkey_client.get_survey_id_by_name(survey_name)
            if not existing_survey_id or existing_title:
                survey_id = self.surveymonkey_client.clone_survey(template_survey_id, survey_name, event_date)
            else:
                survey_id = existing_survey_id

            # Handle case where collector exists and we need to sync the recipient list. Else, create it.
            if self.does_collector_with_this_name_already_exist(survey_id, collector_name):
                print("This exists already. Adding/removing recipients...")
                self.surveymonkey_client.sync_recipients(recipient_emails_on_sheet)
                print("Recipients on collector synced with file.")
            else:
                print(f"Creating new collector on survey: '{survey_id}'")
                collector_send_timestamp = self.calculate_distribution_time_for_event_date(event_date)
                collector_close_timestamp = self.calculate_closing_time_for_collector(event_date)
                collector_id, _ = self.surveymonkey_client.create_collector(
                    survey_id, collector_name, collector_close_timestamp
                )
                # Add recipients to the new collector
                self.surveymonkey_client.add_recipients(collector_id, recipient_emails_on_sheet)
                # Set the reminder on the collector
                self.schedule_reminder_on_a_collector(collector_id, collector_send_timestamp)
                # Schedule the email collector
                self.surveymonkey_client.send_message(collector_id, survey_name, schedule_dt=collector_send_timestamp)
            print(f"Distributed or synced a collector on survey for '{survey_name}'. Moving file to processed folder.")

            # Move sheet to processed folder
            self.google_sheets_client.move_sheet_to_folder(sheet_id, PROCESSED_FOLDER_ID)
            print(f"{sheet_name} moved to processed.")
            print("DONE.")

    def schedule_reminder_on_a_collector(self, collector_id, survey_name, invite_sent_dt):
        body = "Please remember to take your conductor survey. The more responses we have, the more useful the data becomes. Thank you!" 
        self.surveymonkey_client.schedule_reminder_after_collector(
            collector_id,
            subject=f"Reminder: + {survey_name}",
            body=body,
            invite_sent_dt=invite_sent_dt
        )

    def get_id_for_survey_with_this_name_if_it_exists(self, survey_name):
        return self.surveymonkey_client.get_survey_id_by_name(survey_name)

    def does_collector_with_this_name_already_exist(self, survey_id: str, collector_name: str):
        collector_id, collector_url = self.surveymonkey_client.get_collector_by_name(survey_id, collector_name)
        if collector_id and collector_url:
            print("A collector for this conductor+program already exists.")
            return True
        else:
            return False

    def calculate_distribution_time_for_event_date(self, event_date_str):
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
    
    def calculate_closing_time_for_collector(self, event_date_str):
        """
        Given last concert time as string (e.g., '2025-09-16 20:00'),
        returns a timestamp 8 days after the distribution time
        in ISO 8601 UTC format for SurveyMonkey collector close date.
        """
        # Parse event date
        event_dt = datetime.strptime(event_date_str, "%Y-%m-%d %H:%M")
        # Distribution = +100 minutes
        distribution_dt = self.calculate_distribution_time_for_event_date(self, event_dt)
        # Closing = distribution + 8 days
        closing_dt = distribution_dt + timedelta(days=8)
        # Return in ISO 8601 UTC format
        return closing_dt.isoformat() + "Z"
    
    def get_required_template_survey_id(self, event_title: str):
        # TODO polish this?
        print(f"event title is: {event_title}")
        event_title_lowercacse = event_title.lower()
        if "opera" in event_title_lowercacse:
            return SURVEY_TEMPLATES["Seattle Opera"]
        else:
            return SURVEY_TEMPLATES["SSO"]
