import enum
from pathlib import PurePosixPath
from typing import Optional

from django.conf import settings
from django.utils.module_loading import import_string


class StorageProvider(enum.Enum):
    AWS = enum.auto()
    MINIO = enum.auto()
    UNSUPPORTED = enum.auto()


def _get_storage_provider() -> StorageProvider:
    _storage_class = import_string(settings.DEFAULT_FILE_STORAGE)
    try:
        from storages.backends.s3boto3 import S3Boto3Storage

        if _storage_class == S3Boto3Storage or issubclass(_storage_class, S3Boto3Storage):
            return StorageProvider.AWS
    except ImportError:
        pass

    try:
        from minio_storage.storage import MinioMediaStorage

        if _storage_class == MinioMediaStorage or issubclass(_storage_class, MinioMediaStorage):
            return StorageProvider.MINIO
    except ImportError:
        pass

    return StorageProvider.UNSUPPORTED


# internal settings
S3FF_UPLOAD_DURATION = 60 * 60 * 12
# TODO move this here
S3FF_STORAGE_PROVIDER = _get_storage_provider()

# settings inferred from other packages (django-storages and django-minio-storage)
if S3FF_STORAGE_PROVIDER == StorageProvider.AWS:
    S3FF_ACCESS_KEY: Optional[str] = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
    S3FF_SECRET_KEY: Optional[str] = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
    S3FF_BUCKET: Optional[str] = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
    S3FF_REGION: Optional[str] = getattr(settings, 'AWS_S3_REGION_NAME', None)
    S3FF_USE_SSL: Optional[str] = getattr(settings, 'AWS_S3_USE_SSL', True)
    S3FF_ENDPOINT: Optional[str] = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)

    S3FF_UPLOAD_STS_ARN: Optional[str] = getattr(settings, 'S3FF_UPLOAD_STS_ARN', None)
elif S3FF_STORAGE_PROVIDER == StorageProvider.MINIO:
    S3FF_ACCESS_KEY = getattr(settings, 'MINIO_STORAGE_ACCESS_KEY', None)
    S3FF_SECRET_KEY = getattr(settings, 'MINIO_STORAGE_SECRET_KEY', None)
    S3FF_BUCKET = getattr(settings, 'MINIO_STORAGE_MEDIA_BUCKET_NAME', None)
    # Boto needs some region to be set
    S3FF_REGION = 's3ff-minio-fake-region'
    S3FF_USE_SSL = getattr(settings, 'MINIO_STORAGE_USE_HTTPS', False)
    S3FF_ENDPOINT = getattr(settings, 'MINIO_STORAGE_ENDPOINT', None)

    # MinIO needs a valid ARN format, but the content doesn't matter
    # See https://github.com/minio/minio/blob/master/docs/sts/assume-role.md#testing
    S3FF_UPLOAD_STS_ARN = 'arn:s3ff:minio:fake:fake'
else:
    S3FF_ACCESS_KEY = None
    S3FF_SECRET_KEY = None
    S3FF_BUCKET = None
    S3FF_REGION = None
    S3FF_ENDPOINT = None
    S3FF_USE_SSL = None

    S3FF_UPLOAD_STS_ARN = None


# endpoint URLs are required to use boto3 clients
if S3FF_ENDPOINT:
    S3FF_ENDPOINT_URL: Optional[str] = f'http{"s" if S3FF_USE_SSL else ""}://{S3FF_ENDPOINT}'
else:
    S3FF_ENDPOINT_URL = None

# users may need access the store through a different URL than S3FF, i.e. running Minio in docker
# default to the private S3FF_ENDPOINT_URL if it isn't defined explicitly
S3FF_PUBLIC_ENDPOINT_URL: Optional[str] = getattr(
    settings, 'S3FF_PUBLIC_ENDPOINT_URL', S3FF_ENDPOINT_URL
)

# user configurable settings
S3FF_UPLOAD_PREFIX = PurePosixPath(getattr(settings, 'S3FF_UPLOAD_PREFIX', ''))
