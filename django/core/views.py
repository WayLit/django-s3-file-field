import json
import time
import uuid

import boto3
from django.conf import settings
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.http.response import HttpResponseBase
from rest_framework import viewsets
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response

from core.models import Blob
from core.serializers import BlobSerializer


class BlobViewSet(viewsets.ModelViewSet):
    queryset = Blob.objects.all()
    serializer_class = BlobSerializer


# @authentication_classes([TokenAuthentication])
# @permission_classes([IsAuthenticated])
@api_view(['POST'])
@parser_classes([JSONParser])
def finalize_upload(request: Request) -> HttpResponseBase:
    creator = request.user if not request.user.is_anonymous else User.objects.first()
    blob = Blob(creator=creator, resource=request.data['name'])
    blob.save()
    return Response(BlobSerializer(blob).data)


# @authentication_classes([TokenAuthentication])
# @permission_classes([IsAuthenticated])
@api_view(['GET'])
def file_upload_url(request: Request) -> HttpResponseBase:
    bucket_arn = f'arn:aws:s3:::{settings.AWS_STORAGE_BUCKET_NAME}'
    object_key = f'{uuid.uuid4()}/{request.GET.get("name")}'
    upload_policy = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Action': ['s3:PutObject'],
                'Resource': f'{bucket_arn}/{object_key}',
            }
        ],
    }

    # Get temporary security credentials with permission to upload into the
    # object in the S3 bucket. The AWS Security Token Service (STS) provides
    # the credentials when the machine assumes the upload role.
    resp = boto3.client(
        'sts',
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    ).assume_role(
        RoleArn=settings.UPLOAD_STS_ARN,
        RoleSessionName='file-upload-%d' % int(time.time()),
        Policy=json.dumps(upload_policy),
        DurationSeconds=3600,
    )

    credentials = resp['Credentials']

    return JsonResponse(
        {
            'accessKeyId': credentials['AccessKeyId'],
            'secretAccessKey': credentials['SecretAccessKey'],
            'sessionToken': credentials['SessionToken'],
            'bucketName': settings.AWS_STORAGE_BUCKET_NAME,
            'objectKey': object_key,
        }
    )
