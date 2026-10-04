import React from 'react';

function getDocumentTitle(source) {
  return source?.document_title || 'Sumber dokumen';
}

function isWebsiteSource(source) {
  const title = getDocumentTitle(source).toLowerCase();
  return source?.source_type === 'website'
    || title.startsWith('website international muallaf center')
    || title.includes('website imc-mask');
}

function getDisplayTitle(source) {
  return isWebsiteSource(source) ? 'Website IMC-MASK' : getDocumentTitle(source);
}

function formatPage(source) {
  if (source?.reference_label) return source.reference_label;
  if (!source?.page_number) return 'halaman tidak tersedia';
  return `halaman ${source.page_number}`;
}

export default function SourceList({ sources = [], onOpenSource }) {
  if (!sources.length) return null;

  return (
    <div className="source-list" aria-label="Referensi jawaban">
      <span className="source-list-title">Rujukan</span>
      <ul className="source-list-items">
        {sources.map((source, index) => {
          const title = getDocumentTitle(source);
          const displayTitle = getDisplayTitle(source);
          const canOpenDocument = !isWebsiteSource(source) && Boolean(source?.file_name) && Boolean(onOpenSource);

          return (
            <li className="source-citation" key={`${source.chunk_id || source.document_title || 'source'}-${index}`}>
              {canOpenDocument ? (
                <button
                  type="button"
                  className="source-link"
                  onClick={() => onOpenSource(source)}
                  title={`Buka ${title}${source?.page_number ? ` halaman ${source.page_number}` : ''}`}
                >
                  <strong>{displayTitle}</strong>
                </button>
              ) : (
                <strong>{displayTitle}</strong>
              )}
              <span>, {formatPage(source)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
