import json

# Load the Facebook access token from the specified JSON file
with open('C:\Users\Revexn\Cloud-Controlled-Agent\social_media\social_tokens.json') as f:
    tokens = json.load(f)
    facebook_access_token = tokens.get('facebook_access_token')

# Now you can use the facebook_access_token in your script
print(f'Facebook Access Token: {facebook_access_token}')