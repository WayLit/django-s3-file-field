import json
import time
import uuid

import boto3
from django.core.signing import BadSignature, Signer, TimestampSigner
from django.http import JsonResponse
from django.http.response import HttpResponseBase
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser
from rest_framework.request import Request

from . import settings
from . import signals


# @authentication_classes([TokenAuthentication])
# @permission_classes([IsAuthenticated])
@api_view(['POST'])
@parser_classes([JSONParser])
def upload_finalize(request: Request) -> HttpResponseBase:
    name: str = request.data['name']
    status: str = request.data['status']
    object_id: str = request.data['id']
    upload_sig: str = request.data['signature']

    # check if upload_prepare signed this less than max age ago
    tsigner = TimestampSigner()
    if object_id != tsigner.unsign(upload_sig, max_age=settings._JOIST_UPLOAD_DURATION):
        raise BadSignature()

    signals.joist_upload_finalize.send(
        sender=upload_finalize, name=name, status=status, object_key=object_id
    )

    signer = Signer()
    sig = signer.sign(object_id)

    # can be one of aborted|uploaded
    # TODO move file to where it belongs and return the new name

    return JsonResponse({'name': name, 'status': status, 'id': object_id, 'signature': sig})


# @authentication_classes([TokenAuthentication])
# @permission_classes([IsAuthenticated])
@api_view(['POST'])
@parser_classes([JSONParser])
def upload_prepare(request: Request) -> HttpResponseBase:
    name = request.data['name']
    object_key = f'{settings.JOIST_UPLOAD_PREFIX}{uuid.uuid4()}/{name}'

    bucket_arn = f'arn:aws:s3:::{settings._JOIST_BUCKET}'
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

    full_endpoint = None
    if settings._JOIST_ENDPOINT:
        full_endpoint = f'http{"s" if settings._JOIST_USE_SSL else ""}://{settings._JOIST_ENDPOINT}'

    # Get temporary security credentials with permission to upload into the
    # object in the S3 bucket. The AWS Security Token Service (STS) provides
    # the credentials when the machine assumes the upload role.
    client = boto3.client(
        'sts',
        endpoint_url=full_endpoint,
        region_name=settings._JOIST_REGION,
        aws_access_key_id=settings._JOIST_ACCESS_KEY,
        aws_secret_access_key=settings._JOIST_SECRET_KEY,
    )

    resp = client.assume_role(
        RoleArn=settings.JOIST_UPLOAD_STS_ARN or 'arn:xxx:xxx:xxx:xxxx',
        RoleSessionName=f'file-upload-{int(time.time())}',
        Policy=json.dumps(upload_policy),
        DurationSeconds=settings._JOIST_UPLOAD_DURATION,
    )

    credentials = resp['Credentials']
    s3_options = {
        'apiVersion': '2006-03-01',
        'accessKeyId': credentials['AccessKeyId'],
        'secretAccessKey': credentials['SecretAccessKey'],
        'sessionToken': credentials['SessionToken'],
    }
    if settings._JOIST_STORAGE_PROVIDER == 'minio':
        s3_options['s3ForcePathStyle'] = True
        s3_options['endpoint'] = full_endpoint

    signals.joist_upload_prepare.send(sender=upload_prepare, name=name, object_key=object_key)

    signer = TimestampSigner()
    sig = signer.sign(object_key)

    return JsonResponse(
        {
            's3Options': s3_options,
            'bucketName': settings._JOIST_BUCKET,
            'objectKey': object_key,
            'signature': sig,
        }
    )
