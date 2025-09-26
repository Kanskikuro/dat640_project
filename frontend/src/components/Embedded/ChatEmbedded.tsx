import "./ChatEmbedded.css";
import { ReactNode, useState } from "react";
import Playlist from "../Playlist";

export default function ChatEmbedded({ children }: { children: ReactNode }) {
  const [showPlaylist, setShowPlaylist] = useState(true);
  return (
    <div className="row">
      <div className="col-md-6 col-sm-12 mb-3">{children}</div>
      <div className="col-md-6 col-sm-12">
        <div className="d-flex justify-content-between align-items-center mb-2">
          <h5 className="mb-0">Your Playlist</h5>
          <div className="form-check form-switch">
            <input
              className="form-check-input"
              type="checkbox"
              role="switch"
              id="togglePlaylist"
              checked={showPlaylist}
              onChange={(e) => setShowPlaylist(e.target.checked)}
            />
            <label className="form-check-label" htmlFor="togglePlaylist">
              Show
            </label>
          </div>
        </div>
        {showPlaylist && <Playlist />}
      </div>
    </div>
  );
}
