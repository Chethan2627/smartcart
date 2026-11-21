"""
Product Image Storage Service for SmartCart 2.0.
Provides abstracted image upload, validation, and deletion with Cloudinary integration.
Uses asyncio.to_thread for non-blocking execution with the synchronous Cloudinary SDK.
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Set
import cloudinary
import cloudinary.uploader
from app.config import settings
from app.core.exceptions import BadRequestError, SmartCartError


ALLOWED_IMAGE_TYPES: Set[str] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
MAX_IMAGE_SIZE_BYTES: int = 5 * 1024 * 1024  # 5 MB


class ImageStorageService(ABC):
    """Abstract interface for image storage providers."""

    @abstractmethod
    async def upload_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload image bytes and return metadata dict with 'url', 'public_id', etc."""
        pass

    @abstractmethod
    async def delete_image(self, public_id: str) -> bool:
        """Delete an image by its storage public ID."""
        pass


class CloudinaryStorageService(ImageStorageService):
    """
    Cloudinary implementation of ImageStorageService.
    Configured via application settings (CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, etc.).
    """

    def __init__(
        self,
        cloud_name: Optional[str] = None,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        upload_folder: Optional[str] = None,
    ) -> None:
        self.cloud_name = cloud_name or settings.CLOUDINARY_CLOUD_NAME
        self.api_key = api_key or settings.CLOUDINARY_API_KEY
        self.api_secret = api_secret or settings.CLOUDINARY_API_SECRET
        self.upload_folder = upload_folder or settings.CLOUDINARY_UPLOAD_FOLDER

        if settings.CLOUDINARY_URL:
            # Cloudinary handles CLOUDINARY_URL env var natively
            cloudinary.config()
        elif self.cloud_name and self.api_key and self.api_secret:
            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                secure=True,
            )

    def validate_file(self, file_bytes: bytes, content_type: str) -> None:
        """Validate content-type and maximum file size."""
        normalized_content_type = (content_type or "").lower().strip()
        if normalized_content_type not in ALLOWED_IMAGE_TYPES:
            raise BadRequestError(
                f"Unsupported image type '{content_type}'. Allowed formats: JPEG, PNG, WEBP."
            )

        if len(file_bytes) > MAX_IMAGE_SIZE_BYTES:
            max_mb = MAX_IMAGE_SIZE_BYTES // (1024 * 1024)
            actual_mb = len(file_bytes) / (1024 * 1024)
            raise BadRequestError(
                f"Image file size ({actual_mb:.2f} MB) exceeds maximum allowed limit of {max_mb} MB."
            )

        if len(file_bytes) == 0:
            raise BadRequestError("Image file cannot be empty.")

    async def upload_image(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        folder: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validate and upload image to Cloudinary asynchronously.
        Returns standardized dictionary with:
        - url: Secure HTTPS URL
        - public_id: Cloudinary resource public ID
        - format: Image format (jpg, png, webp)
        - width: Image width in pixels
        - height: Image height in pixels
        - bytes: Uploaded size in bytes
        """
        self.validate_file(file_bytes, content_type)

        target_folder = folder or self.upload_folder

        def _sync_upload() -> Dict[str, Any]:
            try:
                response = cloudinary.uploader.upload(
                    file_bytes,
                    folder=target_folder,
                    resource_type="image",
                    overwrite=True,
                )
                return {
                    "url": response.get("secure_url") or response.get("url"),
                    "secure_url": response.get("secure_url"),
                    "public_id": response.get("public_id"),
                    "format": response.get("format"),
                    "width": response.get("width"),
                    "height": response.get("height"),
                    "bytes": response.get("bytes"),
                }
            except Exception as exc:
                raise SmartCartError(f"Cloudinary image upload failed: {str(exc)}") from exc

        return await asyncio.to_thread(_sync_upload)

    async def delete_image(self, public_id: str) -> bool:
        """
        Delete an image resource from Cloudinary by public ID asynchronously.
        """
        if not public_id:
            return False

        def _sync_destroy() -> bool:
            try:
                res = cloudinary.uploader.destroy(public_id, resource_type="image")
                return res.get("result") in ("ok", "not found")
            except Exception as exc:
                # Log or swallow deletion failure to prevent blocking business workflow
                return False

        return await asyncio.to_thread(_sync_destroy)
