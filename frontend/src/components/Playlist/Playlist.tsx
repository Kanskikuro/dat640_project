import React, { useEffect, useState, useCallback, useRef } from "react";
import {
  MDBCard,
  MDBCardHeader,
  MDBCardBody,
  MDBIcon,
  MDBBtn,
  MDBInput,
} from "mdb-react-ui-kit";
import { usePlaylist } from "../../contexts/PlaylistContext";
import "../ChatBox/ChatBox.css";

// improvement :  include disambiguation suggestion 


// Define the Song type for TypeScript
type Song = { artist: string; title: string };

export default function Playlist() {
  // Context functions for managing playlists and songs
  const {
    addSong,
    removeSong,
    onPlaylistResponse,
    switchPlaylist,
    createPlaylist,
    removePlaylist,
    viewPlaylists,
    viewPlaylist,
  } = usePlaylist();

  // State hooks
  const [playlist, setPlaylist] = useState<Song[]>([]);               // Songs in the currently selected playlist
  const [playlists, setPlaylists] = useState<string[]>([]);           // List of playlist names
  const [currentPlaylist, setCurrentPlaylist] = useState<string>(""); // Currently selected playlist
  const [playlistName, setPlaylistName] = useState("");               // Input for creating a new playlist
  const [song, setSong] = useState("");                               // Input for adding a new song
  const [playlistCounts, setPlaylistCounts] = useState<Record<string, number>>({}); // Per-playlist song counts

  // Keep a ref of currentPlaylist to use inside callbacks
  const currentPlaylistRef = useRef(currentPlaylist);
  useEffect(() => {
    currentPlaylistRef.current = currentPlaylist;
  }, [currentPlaylist]);

  // Handle responses from the PlaylistContext
  const handlePlaylistResponse = useCallback(
    (response: any) => {
      if (!response || typeof response !== "object") return;

      switch (response.type) {
        case "songs": // When we receive a list of songs
          const songs = response.data.map((s: string) => {
            const colonIndex = s.indexOf(":");
            if (colonIndex === -1) return { artist: "", title: s.trim() };
            const artist = s.substring(0, colonIndex).trim();
            const title = s.substring(colonIndex + 1).trim();
            return { artist, title };
          });
          setPlaylist(songs); // Update playlist state
          // Update count for the active playlist
          if (currentPlaylistRef.current) {
            setPlaylistCounts((prev) => ({
              ...prev,
              [currentPlaylistRef.current]: songs.length,
            }));
          }
          break;

        case "playlists": // When we receive a list of playlist names
          const playlistList = response.data as string[];
          setPlaylists(playlistList);
          // Ensure counts object has keys for all playlists (keep existing counts)
          setPlaylistCounts((prev) => {
            const next = { ...prev } as Record<string, number>;
            for (const name of playlistList) if (!(name in next)) next[name] = next[name] ?? 0;
            // Remove counts for playlists that no longer exist
            for (const key of Object.keys(next)) if (!playlistList.includes(key)) delete next[key];
            return next;
          });

          // If no playlist is selected, select the first one
          if (!currentPlaylistRef.current && playlistList.length > 0) {
            setCurrentPlaylist(playlistList[0]);
          }

          // If the current playlist was deleted, reset
          if (
            currentPlaylistRef.current &&
            !playlistList.includes(currentPlaylistRef.current)
          ) {
            setCurrentPlaylist(playlistList[0] || "");
            setPlaylist([]);
          }
          break;

        case "added": // Song added
          viewPlaylists(); // Refresh playlists
          if (currentPlaylistRef.current) viewPlaylist(currentPlaylistRef.current);
          // Optimistically bump count for current playlist
          if (currentPlaylistRef.current) {
            const name = currentPlaylistRef.current;
            setPlaylistCounts((prev) => ({ ...prev, [name]: (prev[name] ?? 0) + 1 }));
          }
          break;

        case "removed": // Song removed
          if (currentPlaylistRef.current) viewPlaylist(currentPlaylistRef.current);
          viewPlaylists();
          // Optimistically decrement count for current playlist
          if (currentPlaylistRef.current) {
            const name = currentPlaylistRef.current;
            setPlaylistCounts((prev) => ({ ...prev, [name]: Math.max(0, (prev[name] ?? 0) - 1) }));
          }
          break;

        case "switched": // Playlist switched
          if (response.data) {
            setCurrentPlaylist(response.data);
            viewPlaylist(response.data);
          }
          viewPlaylists();
          break;

        case "created": // New playlist created
          viewPlaylists();
          if (response.data) {
            setCurrentPlaylist(response.data);
            viewPlaylist(response.data);
            // Initialize count to 0 for the new playlist
            const name = response.data as string;
            setPlaylistCounts((prev) => ({ ...prev, [name]: 0 }));
          }
          break;

        case "deleted": // Playlist deleted
          viewPlaylists();
          if (response.data === currentPlaylistRef.current) {
            setCurrentPlaylist("");
            setPlaylist([]);
          }
          // Remove count entry for deleted playlist
          if (response.data) {
            const name = response.data as string;
            setPlaylistCounts((prev) => {
              const next = { ...prev };
              delete next[name];
              return next;
            });
          }
          break;

        default: // Fallback: refresh playlists and songs
          viewPlaylists();
          if (currentPlaylistRef.current) viewPlaylist(currentPlaylistRef.current);
      }
    },
    [viewPlaylists, viewPlaylist]
  );

  // Subscribe to playlist responses
  useEffect(() => {
    const unsubscribe = onPlaylistResponse(handlePlaylistResponse);
    viewPlaylists(); // Load initial playlists
    return () => unsubscribe(); // Cleanup subscription on unmount
  }, [onPlaylistResponse, handlePlaylistResponse, viewPlaylists]);

  // Whenever the current playlist changes, load its songs
  useEffect(() => {
    setPlaylist([]); // Clear old songs
    if (currentPlaylist) viewPlaylist(currentPlaylist); // Load new songs
  }, [currentPlaylist, viewPlaylist]);

  // Handlers for user interactions
  const handleCreatePlaylist = () => {
    const name = playlistName.trim();
    if (!name) return;
    createPlaylist(name);
    setPlaylistName(""); // Clear input
  };

  const handleSwitchPlaylist = (name: string) => {
    if (name === currentPlaylist) return;
    switchPlaylist(name);
  };

  const handleRemovePlaylist = (name: string) => {
    if (!window.confirm(`Delete playlist "${name}"?`)) return;
    removePlaylist(name);
  };

  const handleAddSong = () => {
    const songInput = song.trim();
    if (!songInput || !currentPlaylist) return;
    addSong(songInput, currentPlaylist);
    setSong(""); // Clear input
  };

  const handleRemoveSong = (artist: string, title: string) => {
    if (!currentPlaylist) return;
    removeSong(artist, title);
  };

  return (
    <div className="chat-widget-content">
      <MDBCard
        id="playlistBox"
        className="chat-widget-card"
        style={{ borderRadius: "15px" }}
      >
        <MDBCardHeader
          className="d-flex justify-content-between align-items-center p-3 bg-warning text-dark border-bottom-0"
          style={{ borderTopLeftRadius: "15px", borderTopRightRadius: "15px" }}
        >
          <p className="mb-0 fw-bold">Playlist Manager</p>
        </MDBCardHeader>

        <MDBCardBody style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Playlists Section */}
          <div className="mb-4">
            <h6 className="fw-bold mb-2">
              Your Playlists <span className="badge bg-primary ms-2">{playlists.length}</span>
            </h6>

            {/* Create new playlist input */}
            <div className="d-flex gap-2 mb-2">
              <MDBInput
                label="Playlist name"
                value={playlistName}
                onChange={(e) => setPlaylistName(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleCreatePlaylist()}
                size="sm"
              />
              <MDBBtn
                size="sm"
                color="primary"
                onClick={handleCreatePlaylist}
                disabled={!playlistName.trim()}
              >
                <MDBIcon fas icon="plus" className="me-1" />
                Create
              </MDBBtn>
            </div>

            {/* Display playlists */}
            {playlists.length === 0 ? (
              <div className="alert alert-info mb-0" role="alert">
                <MDBIcon fas icon="info-circle" className="me-2" />
                No playlists yet. Create one to get started!
              </div>
            ) : (
              <ul className="list-group list-group-flush">
                {playlists.map((name) => (
                  <li
                    key={name}
                    className={`list-group-item d-flex justify-content-between align-items-center ${
                      name === currentPlaylist ? "active" : ""
                    }`}
                  >
                    <span
                      onClick={() => handleSwitchPlaylist(name)}
                      style={{ flex: 1, cursor: "pointer" }}
                      className="d-flex align-items-center"
                    >
                      {name === currentPlaylist && (
                        <MDBIcon fas icon="music" className="me-2" />
                      )}
                      {name}
                    </span>
                    <span className="badge bg-primary ms-2">{playlistCounts[name] ?? 0} Songs</span>
                    <button
                      className="btn btn-sm btn-outline-danger"
                      onClick={(e) => {
                        e.stopPropagation(); // Prevent switching playlist when clicking delete
                        handleRemovePlaylist(name);
                      }}
                      title="Delete playlist"
                    >
                      <MDBIcon fas icon="trash" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Songs Section */}
          {currentPlaylist && (
            <div className="mb-3">
              <h6 className="fw-bold mb-2">
                Songs in "{currentPlaylist}" <span className="badge bg-primary ms-2">{playlist.length}</span>
              </h6>

              {/* Add new song */}
              <div className="d-flex gap-2 mb-3">
                <MDBInput
                  label="Artist : Title"
                  value={song}
                  onChange={(e) => setSong(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && handleAddSong()}
                  size="sm"
                  style={{ width: "30ch" }}
                  placeholder="e.g. Kendrick Lamar : HUMBLE."
                />
                <MDBBtn
                  size="sm"
                  color="success"
                  onClick={handleAddSong}
                  disabled={!song.trim()}
                >
                  <MDBIcon fas icon="plus" className="me-1" />
                  Add
                </MDBBtn>
              </div>

              {/* Display songs */}
              {playlist.length === 0 ? (
                <div className="alert alert-secondary mb-0" role="alert">
                  <MDBIcon fas icon="compact-disc" className="me-2" />
                  No songs in this playlist yet.
                </div>
              ) : (
                <ul className="list-group list-group-flush">
                  {playlist.map((item, index) => (
                    <li
                      key={`${item.artist}-${item.title}-${index}`}
                      className="list-group-item d-flex justify-content-between align-items-center"
                    >
                      <span>
                        <MDBIcon fas icon="music" className="me-2 text-muted" />
                        <strong>{item.artist || "Unknown Artist"}</strong> : {item.title}
                      </span>
                      <button
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => handleRemoveSong(item.artist, item.title)}
                        title="Remove song"
                      >
                        <MDBIcon fas icon="times" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* If no playlist selected */}
          {!currentPlaylist && playlists.length > 0 && (
            <div className="alert alert-warning" role="alert">
              <MDBIcon fas icon="hand-pointer" className="me-2" />
              Select a playlist to view and manage songs.
            </div>
          )}
        </MDBCardBody>
      </MDBCard>
    </div>
  );
}
