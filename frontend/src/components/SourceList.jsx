import React from 'react';
import { API_BASE_URL } from '../services/chatApi';

const GOOGLE_DRIVE_FILES = {
  'Mengenal Islam Lebih Dekat bersama Masjid Agung Sunda Kelapa': '1eYXxsaZydPHNZ-qJMU1VSt7RIZTz3sVu',
  'Modul Pembinaan Mualaf': '1fFru9BO9vISZPajq_UA-znMfDoHRc4ap',
  'Tata Cara Ibadah Praktis untuk Mualaf': '1cg3I8OBLLbXvaF0_bi_yrttOSwBInpZb',
};

function getDocumentTitle(source) {
  return source?.document_title || 'Sumber dokumen';
}

function formatPage(source) {
  if (source?.reference_label) return source.reference_label;
  if (!source?.page_number) return 'halaman tidak tersedia';
  return `halaman ${source.page_number}`;
}

function getSourceHref(source) {
  if (source?.file_name) {
    const fileUrl = `${API_BASE_URL}/api/documents/files/${encodeURIComponent(source.file_name)}`;
    if (source?.page_number) {
      return `${fileUrl}#page=${source.page_number}`;
    }
    return fileUrl;
  }

  const title = getDocumentTitle(source);
  const fileId = GOOGLE_DRIVE_FILES[title];

  if (!fileId) return null;

  const baseUrl = `https://drive.google.com/file/d/${fileId}/preview`;
  if (source?.page_number) {
    return `${baseUrl}#page=${source.page_number}`;
  }
  return baseUrl;
}

export default function SourceList({ sources = [] }) {
  if (!sources.length) return null;

  return (
    <div className="source-list" aria-label="Referensi jawaban">
      <span className="source-list-title">Rujukan</span>
      <ul className="source-list-items">
        {sources.map((source, index) => {
          const href = getSourceHref(source);
          const title = getDocumentTitle(source);

          return (
            <li className="source-citation" key={`${source.chunk_id || source.document_title || 'source'}-${index}`}>
              {href ? (
                <a
                  className="source-link"
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  title={`Buka ${title}${source?.page_number ? ` halaman ${source.page_number}` : ''}`}
                >
                  <strong>{title}</strong>
                </a>
              ) : (
                <strong>{title}</strong>
              )}
              <span>, {formatPage(source)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
