import React, { createContext, useContext, useEffect, useState } from "react";
import { useSocket } from "./SocketContext"; // Reuse existing socket context
import { PlaylistContextType } from "../types";

const PlaylistContext = createContext<PlaylistContextType | undefined>(
  undefined
);

export const PlaylistProvider = ({ children }: { children: React.ReactNode }) => {
  const { socket } = useSocket(); // Get the single socket instance
  const [lastResponse, setLastResponse] = useState<string | null>(null);

  // Listen to playlist responses
  useEffect(() => {
    if (!socket) return;

    const handleResponse = (data: { text: string }) => {
      setLastResponse(data.text);
    };

    socket.on("pl_response", handleResponse);

    return () => {
      socket.off("pl_response", handleResponse);
    };
  }, [socket]);

  const createPlaylist = (playlistName: string) => {
    socket?.emit("pl_create", { playlistName });
  };

  const switchPlaylist = (playlistName: string) => {
    socket?.emit("pl_switch", { playlistName });
  };

  const removePlaylist = (playlistName?: string) => {
    socket?.emit("pl_remove_playlist", { playlistName });
  };

  const addSong = (song: string, playlist?: string) => {
    socket?.emit("pl_add", { song, playlist });
  };

  const removeSong = (song: string, playlist?: string) => {
    socket?.emit("pl_remove", { song, playlist });
  };

  const viewPlaylist = (playlistName?: string) => {
    socket?.emit("pl_view", { playlistName });
  };

  const viewPlaylists = () => {
    socket?.emit("pl_view_playlists", {});
  };

  const clearPlaylist = (playlistName?: string) => {
    socket?.emit("pl_clear", { playlistName });
  };

  const onPlaylistResponse = (callback: (text: string) => void) => {
    if (!socket) return () => {};

    const handler = (data: { text: string }) => callback(data.text);
    socket.on("pl_response", handler);

    return () => {
      socket.off("pl_response", handler);
    };
  };

  return (
    <PlaylistContext.Provider
      value={{
        createPlaylist,
        switchPlaylist,
        removePlaylist,
        addSong,
        removeSong,
        viewPlaylist,
        viewPlaylists,
        clearPlaylist,
        onPlaylistResponse,
      }}
    >
      {children}
    </PlaylistContext.Provider>
  );
};

// Custom hook to consume Playlist context
export const usePlaylist = () => {
  const context = useContext(PlaylistContext);
  if (!context) {
    throw new Error("usePlaylist must be used within a PlaylistProvider");
  }
  return context;
};
