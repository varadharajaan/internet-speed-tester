# 1) Show current caller (verify you're root)
aws sts get-caller-identity --output json | jq -r '"AccountId: \(.Account)\nARN: \(.Arn)\nUserId: \(.UserId)"'

# 2) Create new root access key and save it safely
aws iam create-access-key > /home/cloudshell-user/root-new-accesskey.json && \
chmod 600 /home/cloudshell-user/root-new-accesskey.json && \
echo "Saved to /home/cloudshell-user/root-new-accesskey.json (permissions 600)."

# 3) Print the new AccessKeyId and SecretAccessKey (save the secret now!)
jq -r '.AccessKey | "AccessKeyId: \(.AccessKeyId)\nSecretAccessKey: \(.SecretAccessKey)\nUserName: \(.UserName)\nStatus: \(.Status)\nCreateDate: \(.CreateDate)"' /home/cloudshell-user/root-new-accesskey.json

# 4) Print Account ID (and ARN again) explicitly
aws sts get-caller-identity --output json | jq -r '"AccountId: \(.Account)\nARN: \(.Arn)"'
