# StravaWebhooksListener

AWS Lambda function that serves a s a backend for the AWS API Gateway subscribed to events from a Strava App.

## Deployment instructions

This lambda function requires dependencies not available in the AWS SDK for Python. To deploy a new version of the function, follow these steps to create a deployment package (from [here](https://docs.aws.amazon.com/lambda/latest/dg/lambda-python-how-to-create-deployment-package.html#python-package-dependencies)):

1. Deactivate the virtual environment, and zip its dependencies. Then, copy the zip file to this directory

   ```
   deactivate
   cd ~/.virtualenvs/strava-python3/lib/python3.7/site-packages/
   zip -r9 ../../../../function_deps.zip .
   ```

1. Copy the zip file (keep the original for reference) and add the new lambda function:

   ```
   cp function_deps.zip lambda_function.zip
   zip -g lambda_function.zip lambda_function.py
   ```

1. Upload to AWS 

   ```
   aws lambda update-function-code --function-name StravaWebhookListener --zip-file fileb://lambda_function.zip --region <REGION>
   ```

   If successful, you get a response similar to this:

   ```
   {
       "FunctionName": "StravaWebhookListener", 
       "LastModified": "2019-02-26T09:51:02.456+0000", 
       "RevisionId": ".....", 
       "MemorySize": 128, 
       "Environment": {
           "Variables": {
               "CLIENT_SECRET": "...", 
               "CODE": "...", 
               "USER": "...", 
               "CLIENT_ID": "...", 
               "PASSWORD": "..."
           }
       }, 
       "Version": "$LATEST", 
       "Role": "arn:aws:iam::XXXXXX:role/lambda-s3-role", 
       "Timeout": 75, 
       "Runtime": "python3.7", 
       "TracingConfig": {
           "Mode": "PassThrough"
       }, 
       "CodeSha256": "XXXXXXXXX", 
       "Description": "", 
       "VpcConfig": {
           "SubnetIds": [], 
           "VpcId": "", 
           "SecurityGroupIds": []
       }, 
       "CodeSize": 13955811, 
       "FunctionArn": "arn:aws:lambda:REGION:XXXXXXX:function:StravaWebhookListener", 
       "Handler": "lambda_function.lambda_handler"
   }
   ```

## Resources
Full instructions here:

* https://docs.aws.amazon.com/lambda/latest/dg/lambda-python-how-to-create-deployment-package.html
