import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { feedApi, type FeedItem, absoluteFileUrl } from "../api/client";
import "./AchievementDetail.css";

export function AchievementDetail() {
  const { type, id } = useParams<{ type: string; id: string }>();
  const [item, setItem] = useState<FeedItem | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // We fetch the latest feed and find the item by id/type since there's no single GET endpoint yet.
    // In a production app, we would add a GET /feed/:type/:id endpoint.
    feedApi
      .getLatest()
      .then((items) => {
        const found = items.find((i) => i.type === type && i.id === Number(id));
        if (found) setItem(found);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [type, id]);

  if (loading) {
    return <div className="detail-loading">Loading achievement...</div>;
  }

  if (!item) {
    return (
      <div className="detail-error">
        <h2>Achievement not found</h2>
        <Link to="/" className="btn-primary">Back to Home</Link>
      </div>
    );
  }

  const isPdf = item.file_url.toLowerCase().endsWith(".pdf");
  const isImage = /\.(jpg|jpeg|png|gif|webp)$/i.test(item.file_url);

  return (
    <div className="detail-page-container">
      <div className="detail-nav">
        <Link to="/" className="back-link">← Back to Feed</Link>
      </div>
      
      <div className="detail-player-container">
        {isPdf ? (
          <iframe 
            src={absoluteFileUrl(item.file_url)} 
            className="document-player" 
            title={item.title}
          />
        ) : isImage ? (
          <div className="image-player">
            <img src={absoluteFileUrl(item.file_url)} alt={item.title} />
          </div>
        ) : (
          <div className="generic-player">
            <a href={absoluteFileUrl(item.file_url)} target="_blank" rel="noopener noreferrer" className="btn-primary">
              Download Document
            </a>
          </div>
        )}
      </div>

      <div className="detail-info-container">
        <h1 className="detail-title">{item.title}</h1>
        
        <div className="detail-meta-row">
          <div className="detail-owner">
            <div className={`owner-avatar avatar-${item.type}`}>
              {(item.student_name || "F").charAt(0).toUpperCase()}
            </div>
            <div className="owner-info">
              <span className="owner-name">{item.student_name || "Faculty Member"}</span>
              <span className="owner-type">{item.owner_type === "student" ? "Student" : "Faculty"}</span>
            </div>
          </div>
          
          <div className="detail-stats">
            <span className="detail-category">{item.category}</span>
            <span className="detail-date">
              Verified on {item.verified_at ? new Date(item.verified_at).toLocaleDateString() : "N/A"}
            </span>
          </div>
        </div>
        
        <div className="detail-description">
          <p>
            This <strong>{item.category}</strong> was achieved by <strong>{item.student_name || "a Faculty Member"}</strong>.
            The document has been officially verified by the institution's administration.
          </p>
        </div>
      </div>
    </div>
  );
}
