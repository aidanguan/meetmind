import os
import uuid
import oss2
from typing import Tuple

def _get_bucket() -> oss2.Bucket:
    access_key_id = os.getenv("OSS_ACCESS_KEY_ID", "")
    access_key_secret = os.getenv("OSS_ACCESS_KEY_SECRET", "")
    endpoint = os.getenv("OSS_ENDPOINT", "")
    bucket_name = os.getenv("OSS_BUCKET", "")
    auth = oss2.Auth(access_key_id, access_key_secret)
    return oss2.Bucket(auth, endpoint, bucket_name)

class OSSService:
    @staticmethod
    def upload_file(file_path: str) -> Tuple[str, str]:
        bucket = _get_bucket()
        prefix = os.getenv("OSS_PREFIX", "meetmind/recordings")
        ext = os.path.splitext(file_path)[1].lower()
        object_name = f"{prefix}/{uuid.uuid4()}{ext}"
        with open(file_path, "rb") as f:
            bucket.put_object(object_name, f)
        url = bucket.sign_url('GET', object_name, 3600)
        return object_name, url
