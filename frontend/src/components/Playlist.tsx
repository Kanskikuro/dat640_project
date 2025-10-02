import React, { useState } from "react";
import { usePlaylist } from "../contexts/PlaylistContext";
import { MDBIcon } from "mdb-react-ui-kit";

export default function Playlist() {
  const { items, removeItem, clear, reorder } = usePlaylist();
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const onDragStart = (index: number) => () => setDragIndex(index);
  const onDragOver = (e: React.DragEvent<HTMLLIElement>) => e.preventDefault();
  const onDrop = (index: number) => (e: React.DragEvent<HTMLLIElement>) => {
    e.preventDefault();
    if (dragIndex === null || dragIndex === index) return;
    reorder(dragIndex, index);
    setDragIndex(null);
  };

  return (
    <div className="playlist-container">
      <div className="d-flex justify-content-between align-items-center mb-2">
        <h6 className="mb-0">Playlist</h6>
        <button className="btn btn-sm btn-outline-danger" onClick={clear} disabled={items.length === 0}>
          <MDBIcon fas icon="trash" className="me-1" /> Clear
        </button>
      </div>
      {items.length === 0 ? (
        <p className="text-muted mb-0">Your playlist is empty. Add songs from chat or search.</p>
      ) : (
        <ul className="list-group">
          {items.map((it, idx) => (
            <li
              key={it.id}
              className="list-group-item d-flex align-items-center justify-content-between"
              draggable
              onDragStart={onDragStart(idx)}
              onDragOver={onDragOver}
              onDrop={onDrop(idx)}
              style={{ cursor: "grab" }}
            >
              <div className="d-flex align-items-center">
                <span className="text-muted me-2" style={{ width: 18, display: "inline-block", textAlign: "right" }}>
                  {idx + 1}
                </span>
                <MDBIcon fas icon="grip-vertical" className="me-2 text-muted" />
                <div>
                  <div className="fw-semibold">{it.title}</div>
                  <div className="small text-muted">{it.artist}</div>
                </div>
              </div>
              <div className="d-flex align-items-center">
                {it.spotifyUri && (
                  <a className="btn btn-sm btn-outline-secondary me-2" href={it.spotifyUri} target="_blank" rel="noreferrer">
                    <MDBIcon fab icon="spotify" />
                  </a>
                )}
                <button className="btn btn-sm btn-outline-danger" onClick={() => removeItem(it.id)}>
                  <MDBIcon fas icon="times" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
