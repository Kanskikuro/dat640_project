import "./ChatEmbedded.css";
import { ReactNode, useState } from "react";
import Playlist from "../Playlist/Playlist";

export default function ChatEmbedded({ children }: { children: ReactNode }) {
  const [showPlaylist, setShowPlaylist] = useState(true);
  return (
    <div className="row">
      <div className="col-md-6 col-sm-12 mb-3">{children}</div>
      <div className="col-md-6 col-sm-12">
        <div className="d-flex justify-content-between align-items-center mb-2">
        </div>
        {showPlaylist && <Playlist />}
      </div>
    </div>
  );
}
