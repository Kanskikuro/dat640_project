import "./ChatWidget.css";
import { useState, MouseEvent, ReactNode } from "react";
import { MDBIcon } from "mdb-react-ui-kit";
<<<<<<< HEAD
import Playlist from "../Playlist/Playlist";

export default function ChatWidget({ children }: { children: ReactNode }) {
  const [isChatBoxOpen, setIsChatBoxOpen] = useState<boolean>(false);
  const [tab, setTab] = useState<"chat" | "playlist">("chat");
=======

export default function ChatWidget({ children }: { children: ReactNode }) {
  const [isChatBoxOpen, setIsChatBoxOpen] = useState<boolean>(false);
>>>>>>> upstream/main

  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    setIsChatBoxOpen(isChatBoxOpen ? false : true);
  }

  return (
    <div className="chat-widget-container">
      <div className="chat-widget-icon">
        <a href="#!" onClick={handleClick} className="text-muted">
          <MDBIcon fas icon="robot" />
        </a>
      </div>
<<<<<<< HEAD
      <div className="chat-widget-box">
        {isChatBoxOpen && (
          <div className="d-flex flex-column" style={{ height: "100%" }}>
            <div className="d-flex border-bottom mb-2">
              <button
                className={`btn btn-sm ${tab === "chat" ? "btn-primary" : "btn-outline-primary"} me-2`}
                onClick={() => setTab("chat")}
              >
                <MDBIcon fas icon="comments" className="me-1" /> Chat
              </button>
              <button
                className={`btn btn-sm ${tab === "playlist" ? "btn-primary" : "btn-outline-primary"}`}
                onClick={() => setTab("playlist")}
              >
                <MDBIcon fas icon="music" className="me-1" /> Playlist
              </button>
            </div>
            <div style={{ overflow: "auto" }}>
              {tab === "chat" ? children : <Playlist />}
            </div>
          </div>
        )}
      </div>
=======
      <div className="chat-widget-box">{isChatBoxOpen && children}</div>
>>>>>>> upstream/main
    </div>
  );
}
