from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class StaticStorage(S3Boto3Storage):
    """
    S3 storage for static files.

    Public read — static assets (CSS, JS) are served directly
    from S3/CloudFront without pre-signed URLs.
    No cache-busting suffix: WhiteNoise handles that in development.
    """

    location = "static"
    default_acl = "public-read"
    querystring_auth = False
    file_overwrite = True


class MediaStorage(S3Boto3Storage):
    """
    S3 storage for user-uploaded media files.

    Private by default — access is via pre-signed URLs (1-hour expiry).
    file_overwrite=False: preserves original on duplicate filename
    (UUID-based paths make collisions virtually impossible, but safe anyway).
    """

    location = "media"
    default_acl = "private"
    querystring_auth = True
    querystring_expire = 3600
    file_overwrite = False