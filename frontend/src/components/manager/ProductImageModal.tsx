import React, { useState, useRef } from 'react';
import { X, UploadCloud, Trash2, Image as ImageIcon, AlertCircle, Loader2, Check } from 'lucide-react';
import type { ManagerProduct } from '../../types';
import { uploadManagerProductImage, deleteManagerProductImage } from '../../api/client';
import { getProductImage } from '../../utils/format';

interface ProductImageModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  product: ManagerProduct | null;
  storeId?: string;
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024; // 5MB backend limit
const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

export const ProductImageModal: React.FC<ProductImageModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  product,
  storeId,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen || !product) return null;

  const currentImage = product.image?.secure_url || product.image?.url;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setSuccessMsg(null);
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError('Unsupported file format. Please upload JPEG, PNG, or WEBP.');
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setError('File size exceeds the 5MB maximum limit.');
      return;
    }

    setSelectedFile(file);
    const objectUrl = URL.createObjectURL(file);
    setPreviewUrl(objectUrl);
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setError(null);
    setSuccessMsg(null);

    try {
      await uploadManagerProductImage(product.id, selectedFile, storeId);
      setSuccessMsg('Product image uploaded successfully to Cloudinary.');
      setSelectedFile(null);
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
      onSuccess();
    } catch (err: unknown) {
      console.error('Upload image error:', err);
      setError(err instanceof Error ? err.message : 'Failed to upload image.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDelete = async () => {
    setIsDeleting(true);
    setError(null);
    setSuccessMsg(null);

    try {
      await deleteManagerProductImage(product.id, storeId);
      setSuccessMsg('Product image removed from Cloudinary.');
      onSuccess();
    } catch (err: unknown) {
      console.error('Delete image error:', err);
      setError(err instanceof Error ? err.message : 'Failed to remove image.');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleClose = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setSelectedFile(null);
    setError(null);
    setSuccessMsg(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-black/60 backdrop-blur-sm overflow-y-auto animate-fade-in">
      <div
        className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-100 overflow-hidden my-8"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-5 border-b border-gray-100 bg-gray-50/70 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center">
              <ImageIcon className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-bold text-gray-900 text-base">Product Photography</h3>
              <p className="text-xs text-gray-500 font-mono">SKU: {product.sku}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 sm:p-6 space-y-4">
          {error && (
            <div className="p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {successMsg && (
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-start gap-2">
              <Check className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Current Live Image */}
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
              Current Live Image
            </label>
            <div className="relative rounded-xl border border-gray-200 bg-gray-50 overflow-hidden aspect-video flex items-center justify-center">
              <img
                src={currentImage || getProductImage(product.sku, product.category)}
                alt={product.name}
                className="max-h-full max-w-full object-contain"
              />
              {currentImage && (
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={isDeleting || isUploading}
                  className="absolute top-2 right-2 p-1.5 rounded-lg bg-red-600/90 hover:bg-red-700 text-white shadow-sm transition disabled:opacity-50"
                  title="Remove image from Cloudinary"
                >
                  {isDeleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                </button>
              )}
            </div>
            {product.image && (
              <div className="mt-1 flex items-center justify-between text-[10px] text-gray-400 font-mono">
                <span>Format: {product.image.format?.toUpperCase() || 'JPEG'}</span>
                <span>
                  {product.image.width && product.image.height
                    ? `${product.image.width}×${product.image.height}px`
                    : ''}
                </span>
                <span>
                  {product.image.bytes ? `${(product.image.bytes / 1024).toFixed(1)} KB` : ''}
                </span>
              </div>
            )}
          </div>

          {/* File Picker & Upload Section */}
          <div className="pt-2 border-t border-gray-100">
            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
              Upload New Image to Cloudinary
            </label>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handleFileChange}
              className="hidden"
            />

            {previewUrl ? (
              <div className="space-y-3">
                <div className="relative rounded-xl border-2 border-emerald-500 bg-emerald-50/20 overflow-hidden aspect-video flex items-center justify-center">
                  <img src={previewUrl} alt="Preview" className="max-h-full max-w-full object-contain" />
                  <span className="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 text-white text-[10px] font-semibold">
                    New Preview: {selectedFile?.name} ({(selectedFile!.size / 1024).toFixed(1)} KB)
                  </span>
                </div>

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (previewUrl) URL.revokeObjectURL(previewUrl);
                      setPreviewUrl(null);
                      setSelectedFile(null);
                    }}
                    disabled={isUploading}
                    className="flex-1 py-2 px-3 rounded-xl border border-gray-200 text-gray-700 text-xs font-semibold hover:bg-gray-50 transition"
                  >
                    Cancel Selection
                  </button>
                  <button
                    type="button"
                    onClick={handleUpload}
                    disabled={isUploading}
                    className="flex-1 py-2 px-3 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-xs transition flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        <span>Uploading...</span>
                      </>
                    ) : (
                      <>
                        <UploadCloud className="w-3.5 h-3.5" />
                        <span>Confirm Upload</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isDeleting}
                className="w-full py-6 px-4 rounded-xl border-2 border-dashed border-gray-300 hover:border-emerald-500 hover:bg-emerald-50/30 text-gray-600 transition flex flex-col items-center justify-center gap-1.5 cursor-pointer"
              >
                <UploadCloud className="w-6 h-6 text-emerald-600" />
                <span className="text-xs font-semibold text-gray-800">
                  Click to select replacement image
                </span>
                <span className="text-[10px] text-gray-400">
                  Supports JPEG, PNG, WEBP • Max 5MB
                </span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
