import json
import boto3
import botocore
import os
from botocore.vendored import requests
import datetime
from stravaweblib import WebClient, DataFormat


###################################################################
# Save json Strava oauth payload to the tokens file
###################################################################
# path_to_tokens_file : path and name of the tokens file, in the lambda environment
def save_tokens_file_to_s3(path_to_tokens_file) :
    bucket_name = os.environ['TOKENS_BUCKET_NAME']
    s3 = boto3.resource("s3")
    filename = os.path.basename(path_to_tokens_file)
    s3_path = "tokens/" + filename
    print("Uploading " + path_to_tokens_file + " to S3 at " + s3_path)
    s3.Bucket(bucket_name).upload_file(path_to_tokens_file, s3_path)
    print("File uploaded to S3 bucket " + bucket_name + " as " + s3_path)

###################################################################
# Download Strava tokens json file to lambda /tmp/ folder
###################################################################
# tokens_filename : name of the tokens file
# Note: it throws if the requested file is not found
def download_tokens_file_from_s3(target_folder) :
    tokens_filename = "tokens.json"
    bucket_name = os.environ['TOKENS_BUCKET_NAME']
    s3 = boto3.resource("s3")
    s3_path = "tokens/" + tokens_filename
    print("Downloading tokens file from S3 " + bucket_name + " from " + s3_path + " into " + target_folder + tokens_filename)
    s3.Bucket(bucket_name).download_file(s3_path, target_folder + tokens_filename)
    print("File downloaded from S3 " + s3_path + " saved as " + target_folder + tokens_filename)

###################################################################
# Get initial access and refresh tokens to access the Strava API
###################################################################
# To obtain the 'code' value, navigate to this url (note the client_id embedded in the request)
# http://www.strava.com/oauth/authorize?client_id=[REPLACE WITH CLIENT ID]&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=read
# Note that the scope of the tocken can be changes by editing the url above. A description of the required scope for different access levels is explained here:
# http://developers.strava.com/docs/authentication/
# For example:
# http://www.strava.com/oauth/authorize?client_id=[CLIENT ID]&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=force&scope=activity:read_all
# The 'code' value is returned in the url after the authorisation is accepted, as described here:
# http://developers.strava.com/docs/getting-started/#oauth
# The access code is meant to be used only once: after getting the initial access and refresh tokens,
# new access tokens should be requested using the refresh token.
def get_initial_tokens_file(client_id, client_secret, code, tokens_filepath) :
    # OAuth: get a token. make sure you did the manual steps explained above, in order to get a code.
    # Client id and client secret are obtained when creating a strava app. That's the first step (manual)
    oauth_endpoint = 'https://www.strava.com/oauth/token'
    oauth_parameters = {
            "client_id": client_id, 
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code"
    }

    oauth_response = requests.post(oauth_endpoint, params = oauth_parameters)
    response_content = json.loads(oauth_response.content.decode("utf-8"))
    print(response_content)
    if oauth_response.status_code != 200:
        raise Exception("OAuth response was not successful")

    # Save the response to JSON
    tokens_filepath = "tokens.json"
    with open(tokens_filepath, 'w') as outfile:
        json.dump(response_content, outfile)


def get_initial_tokens() :
    # Get the initial tokens in a file
    client_id = os.environ['CLIENT_ID']
    client_secret = os.environ['CLIENT_SECRET']
    code = os.environ['CODE']
    tokens_filepath = "/tmp/tokens.json"
    get_initial_tokens_file(client_id, client_secret, code, "/tmp/tokens.json")

    # Save the JSON file to S3
    save_tokens_file_to_s3(tokens_filepath)


###################################################################
# Get a valid access token to access the Strava API
###################################################################
# If the access token in the tokens file is still valid, it is returned by this function.
# If it has alreday expired, the refresh token in the tokens file is used to request another access token.
# The new access and refresh tokens are stored in the tokens file so that they can be used in the next
# request.
def get_access_token() :
    downloads_folder = "/tmp/"
    tokens_filepath = "/tmp/tokens.json"
    # Retrieve the tokens file from S3
    try:
        download_tokens_file_from_s3(downloads_folder)
    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == "404" or  e.response['Error']['Code'] == "403":
            print("The tokens.json file does not exist: requesting initial tokens")
            # This function should store the tokens in S3, but it would also
            # have made them available locally before upload, so there is no need to download again
            # It is guaranteed that the token in here is valid (unless the initial request went wrong)
            get_initial_tokens()
        else:
            raise

    # Retrieve the tokens from file
    json_file = open(tokens_filepath, "r")
    data = json.load(json_file)
    json_file.close()

    expiration_epoch = data['expires_at']
    access_token = data['access_token']
    refresh_token = data['refresh_token']

    # Check whether the access token is still valid
    current_epoch = datetime.datetime.now().timestamp()
    if expiration_epoch >= current_epoch :
        print("The current token is still valid (expiration epoch = {expiration}, "
              "current epoch = {now}".format(expiration=expiration_epoch, now=current_epoch))
        return access_token

    # If the access token has expired (they expire after 6 hours), request a new access and refresh tokens
    oauth_endpoint = 'https://www.strava.com/oauth/token'
    client_id = os.environ['CLIENT_ID']
    client_secret = os.environ['CLIENT_SECRET']
    oauth_parameters = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type" : "refresh_token",
        "refresh_token": refresh_token
    }

    oauth_response = requests.post(oauth_endpoint, params = oauth_parameters)
    print(oauth_response)
    if oauth_response.status_code != 200:
        raise Exception("OAuth response was not successful: could not refresh the access token")
    # Save the response to JSON
    response_content = json.loads(oauth_response.content.decode("utf-8"))
    print(response_content)
    with open(tokens_filepath, 'w') as outfile:
        json.dump(response_content, outfile)

    # Save the JSON file to S3 (replacing previous tokens file)
    save_tokens_file_to_s3(tokens_filepath)


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
    info = json.loads(activities_response.content.decode("utf-8"))
    print(info)
    if activities_response.status_code != 200:
        raise Exception("Could not access the activity info")

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