import React from 'react';
import { ArrowLeft, Download, ExternalLink, FileText } from 'lucide-react';
import { API_BASE_URL } from '../services/chatApi';

function documentUrl(fileName, pageNumber) {
  const baseUrl = `${API_BASE_URL}/api/documents/files/${encodeURIComponent(fileName)}`;
  return pageNumber ? `${baseUrl}#page=${pageNumber}&view=Fit` : baseUrl;
}

export default function DocumentViewer({ source, onBack }) {
  const fileName = source?.fileName || '';
  const title = source?.title || 'Dokumen rujukan';
  const pageNumber = source?.pageNumber || null;
  const viewUrl = documentUrl(fileName, pageNumber);
  const downloadUrl = `${API_BASE_URL}/api/documents/download/${encodeURIComponent(fileName)}`;

  return (
    <main className="document-viewer-page">
      <section className="document-viewer-shell">
        <header className="document-viewer-header">
          <button className="viewer-back-button" type="button" onClick={onBack}>
            <ArrowLeft size={19} />
            <span>Kembali ke Muallaf Bot</span>
          </button>
          <div className="viewer-document-heading">
            <FileText size={22} />
            <div>
              <h1>{title}</h1>
              <p>{pageNumber ? `Rujukan halaman ${pageNumber}` : 'Dokumen rujukan'}</p>
            </div>
          </div>
          <nav className="viewer-actions" aria-label="Aksi dokumen">
            <a href={viewUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={17} />
              <span>Buka tab baru</span>
            </a>
            <a href={downloadUrl}>
              <Download size={17} />
              <span>Unduh</span>
            </a>
          </nav>
        </header>

        <div className="document-frame-wrap">
          <iframe className="document-frame" src={viewUrl} title={`${title} PDF`} />
          <p className="document-frame-fallback">
            PDF tidak tampil? <a href={viewUrl} target="_blank" rel="noreferrer">Buka dokumen di tab baru</a>.
          </p>
        </div>
      </section>
    </main>
  );
}
