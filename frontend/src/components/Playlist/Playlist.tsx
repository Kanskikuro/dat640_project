import React, { useEffect, useState } from "react";
import {
  MDBCard,
  MDBCardHeader,
  MDBCardBody,
  MDBCardFooter,
  MDBIcon,
  MDBBtn,
  MDBInput,
} from "mdb-react-ui-kit";
import { usePlaylist } from "../../contexts/PlaylistContext";
import "../ChatBox/ChatBox.css";


export default function Playlist() {
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
type Song = { artist: string; title: string };
  
  const [playlist, setPlaylist] = useState<Song[]>([]);
  const [playlistName, setPlaylistName] = useState("");
  
  const [playlists, setPlaylists] = useState<string[]>([]);
  const [currentPlaylist, setCurrentPlaylist] = useState<string>("");
  const [song, setsong] = useState("");


  // Listen for playlist content responses
useEffect(() => {
  const unsubscribe = onPlaylistResponse((message) => {

  try {
    // If the server sends JSON directly, no need to JSON.parse again
    const data = message;

    if (Array.isArray(data)) {
      if (data.length > 0 && typeof data[0] === "string") {
        setPlaylists(data);
      } else {
        setPlaylist(data as Song[]);
      }
    } else {
      console.warn("Unexpected playlist response format:", data);
    }
  } catch (e) {
    console.error("Failed to parse playlist response:", message);
  }
});

  viewPlaylists(); // request the playlists from server

  return typeof unsubscribe === "function" ? unsubscribe : () => {};
}, [onPlaylistResponse, viewPlaylists]);

  const handleRemovePlaylist = (name: string) => {
    removePlaylist(name); 

    const remainingPlaylists = playlists.filter(p => p !== name);

    // Update the playlists state
    setPlaylists(remainingPlaylists);

    if (remainingPlaylists.length > 0) {
      const nextPlaylist = remainingPlaylists[0];
      switchPlaylist(nextPlaylist);
      setCurrentPlaylist(nextPlaylist);
      viewPlaylist(nextPlaylist);
    } else {
      setCurrentPlaylist("");
      setPlaylist([]); // Clear songs
    }

    viewPlaylists(); // optional, if you want to sync from server
  };


  const handleSwitchPlaylist = (name: string) => {
    switchPlaylist(name);
    setCurrentPlaylist(name);
    viewPlaylist(name);
    viewPlaylists();
  };

  const handleCreatePlaylist = () => {
    if (!playlistName) return;
    createPlaylist(playlistName);
    setCurrentPlaylist(playlistName);
    viewPlaylist(playlistName);
    viewPlaylists();
    setPlaylistName("");
  };

  const handleAddSong = () => {
    if (!currentPlaylist) {
      alert("Select a playlist first!");
      return;
    }
    if (!song) return;
    addSong(song, currentPlaylist); 
    viewPlaylist(currentPlaylist);
  };
  const handleRemoveSong = () => {
  if (!currentPlaylist) {
    alert("Select a playlist first!");
    return;
  }
  if (!song) return;
  removeSong(song, currentPlaylist); 
  viewPlaylist(currentPlaylist);
  setsong("");
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
          style={{
            borderTopLeftRadius: "15px",
            borderTopRightRadius: "15px",
          }}
        >
          <p className="mb-0 fw-bold">Playlist</p>

        </MDBCardHeader>

        <MDBCardBody>
          {/* Playlist creation input */}
          <div className="mb-3 d-flex gap-2">
            <MDBInput
              label="Playlist name"
              value={playlistName}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setPlaylistName(e.target.value)
              }
              size="sm"
            />
            <MDBBtn size="sm" color="primary" onClick={handleCreatePlaylist}>
              Create
            </MDBBtn>
          </div>
          {/* Display all playlists */}
          <div className="mb-3">
            <h6>Playlists:</h6>
            {playlists.length === 0 ? (
              <p className="text-muted">No playlists yet.</p>
            ) : (
              <ul className="list-group list-group-flush">
                {playlists.map((name) => (
                  <li
                    key={name}
                    className={`list-group-item d-flex justify-content-between align-items-center ${
                      name === currentPlaylist ? "bg-light fw-bold" : ""
                    }`}
                    style={{ cursor: "pointer" }}
                  >
                    <span onClick={() => handleSwitchPlaylist(name)} style={{ flex: 1 }}>
                      {name}
                      {name === currentPlaylist && <MDBIcon fas icon="check" className="ms-2" />}
                    </span>
                    <button
                      className="btn btn-sm btn-outline-danger ms-2"
                      onClick={() => {
                        handleRemovePlaylist(name); // You need to implement this in your context
                        if (name === currentPlaylist) setCurrentPlaylist("");
                          viewPlaylists(); // Refresh playlist list
                      }}
                    >
                      <MDBIcon fas icon="trash" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>


          {/* Display songs in the current playlist */}
          <div className="mb-3">
            <h6>Songs in playlist "{currentPlaylist}":</h6>
            {playlist.length === 0 ? (
              <p className="text-muted">No songs added yet.</p>
            ) : (
              <ul className="list-group list-group-flush">
                {playlist.map((item, index) => (
                  <li
                    key={index}
                    className="list-group-item d-flex justify-content-between align-items-center"
                  >
                    <span>
                      {item.artist} - {item.title}
                    </span>
                    <button
                      className="btn btn-sm btn-outline-danger"
                      onClick={() =>
                        handleRemoveSong()
                      }
                    >
                      <MDBIcon fas icon="times" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {/* Add new song input */}
          <div className="mb-3 d-flex gap-2">
            <MDBInput
              label="song"
              value={song}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setsong(e.target.value)}
              size="sm"
            />
            <MDBBtn size="sm" color="success" onClick={handleAddSong}>
              Add Song
            </MDBBtn>
          </div>
          </div>
        </MDBCardBody>

        <MDBCardFooter className="text-muted d-flex justify-content-end">
          <p className="mb-0">{playlist.length} song(s)</p>
        </MDBCardFooter>
      </MDBCard>
    </div>
  );
}
