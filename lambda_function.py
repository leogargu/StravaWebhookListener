import json
import boto3
import os
from botocore.vendored import requests
import datetime
from stravaweblib import WebClient, DataFormat

###################################################################
# generate an access token to access the Strava API
###################################################################
def get_access_token() :
    # OAuth: get a token. make sure you did the manual steps explained above, in order to get a code.
    # Client id and client secret are obtained when creating a strava app. That's the first step (manual)
    oauth_endpoint = 'https://www.strava.com/oauth/token'
    client_id = os.environ['CLIENT_ID']
    client_secret = os.environ['CLIENT_SECRET']
    code = os.environ['CODE']
    oauth_parameters = {
            "client_id": client_id, 
            "client_secret": client_secret, 
            "code": code
        }
    
    oauth_response = requests.post(oauth_endpoint, params = oauth_parameters)
    if oauth_response.status_code != 200:
        raise Exception("OAuth response was not successful")
        
    response_content = json.loads(oauth_response.content.decode("utf-8"))
    access_token = response_content['access_token']
    return access_token

###################################################################
# Given an activity id, it gets information about the activity
# This includes:
# 'name' - name of the activity
# 'external_id' - name of the original fit file uploaded to Strava
###################################################################
def get_activity_info(id, token) :
    url_endpoint = 'https://www.strava.com/api/v3'
    url_what = '/activities/' + str(id)  

    headers = {"Authorization": "Bearer " + token}
    
    activities_response = requests.get(url_endpoint + url_what, headers=headers)
    if activities_response.status_code != 200:
        raise Exception("Could not access the activity info")

    info = json.loads(activities_response.content.decode("utf-8"))
    return info

###################################################################
# Downloads the original fit file uploaded to Strava.
# It automatically names it based on the activity name
###################################################################
def download_file(activity_id, access_token, user, password) :
    # Log in (requires API token and email/password for the site)
    client = WebClient(access_token=access_token, email=user, password=password)

    # Get the filename and data stream for the activity data
    data = client.get_activity_data(activity_id, fmt=DataFormat.ORIGINAL)

    downloaded_file = "/tmp/" + data.filename
    # Save the activity data to disk using the server-provided filename
    with open(downloaded_file, 'wb') as f:
        for chunk in data.content:
            if not chunk:
                break
            f.write(chunk)
    return downloaded_file


#####################################
####       Lambda function       ####
#####################################
def lambda_handler(event, context):

    print(event)
    bucket_name = "athletelab-fit-files"
    response = {"statusCode": 200}

    # A GET request is used to stablish the authentication/handshake (one-off)
    if event['httpMethod'] == 'GET' :
        event_json = json.dumps(event)
        if "hub.mode" in event_json and "queryStringParameters" in event_json:
            if event['queryStringParameters']['hub.mode'] == "subscribe" :
                challenge = event['queryStringParameters']['hub.challenge']
                challenge_string = "{'hub.challenge':'"+ str(challenge) +"'}"
                payload = {
                    'hub.challenge': challenge
                }
                jsonpayload = json.dumps(payload, indent=2)
                response = {"statusCode": 200, "body": jsonpayload }
    
    # A POST request contains information on the event that has just happened in Strava
    if event['httpMethod'] == 'POST' :
        body_json = json.loads(event['body'])
        if body_json['object_type'] == "activity" :
            activity_id = body_json['object_id']
            if body_json['aspect_type'] == 'create':
                print("New activity uploaded to strava: "+ str(activity_id))
                
                # Retrieve credentials
                access_token = get_access_token()
                user =  os.environ['USER']
                password = os.environ['PASSWORD']
                print("Retrieving activity information")                
                activity_info = get_activity_info(activity_id, access_token)
                activity_name = activity_info['name']
                activity_external_id = activity_info['external_id']
                print("Activity name is "+ activity_name + ", Original fit file was named " + activity_external_id)
                
                # Download the original fit file. Name it as the activity, without spaces
                print("Downloading original file")
                lambda_path = download_file(activity_id, access_token, user, password)
                file_name = os.path.basename(lambda_path)
                file_downloaded = os.path.exists(lambda_path)
                print("Has the file" + file_name + " been downloaded?: " + str(file_downloaded))

                # Save the file into the S3 bucket, getting it ready to be converted to csv
                print("Uploading file to S3, with metadata")
                s3_path = "to_convert/" + str(activity_id) + "-" + file_name
                s3 = boto3.resource("s3")
                metadata = {"Metadata": {"Original_Name":activity_name, "External_Id":activity_external_id, "Activity_Id": str(activity_id)}}
                print(metadata)
                s3.Bucket(bucket_name).upload_file(lambda_path, s3_path, ExtraArgs=metadata)
                print("File uploaded to S3 bucket " + bucket_name + " as " + s3_path)
            
            elif body_json['aspect_type'] == 'delete' :
                print("An activity was deleted! Won't do anything")
                print("Activity info")
                print(event["body"])

            elif body_json['aspect_type'] == 'update':
                print("Something has changed! Won't do anything")
                print(event["body"])

            else:
                print("Unrecognised aspect_type value")
                response = {"statusCode": 501}

    print(response)
    return response