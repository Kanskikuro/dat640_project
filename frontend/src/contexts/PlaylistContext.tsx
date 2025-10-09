import React, { createContext, useContext, useEffect, useState } from "react";
import { useSocket } from "./SocketContext";
import { PlaylistContextType } from "../types";

const PlaylistContext = createContext<PlaylistContextType | undefined>(
  undefined
);

export const PlaylistProvider = ({ children }: { children: React.ReactNode }) => {
  const { socket } = useSocket();

  useEffect(() => {
    if (!socket) return;

    // Just relay the response - don't process it here
    const handleResponse = (data: any) => {
      console.log("PlaylistContext received response:", data);
    };

    socket.on("pl_response", handleResponse);

    return () => {
      socket.off("pl_response", handleResponse);
    };
  }, [socket]);

  const createPlaylist = (playlistName: string) => {
    console.log("Creating playlist:", playlistName);
    socket?.emit("pl_create", { playlistName });
  };

  const switchPlaylist = (playlistName: string) => {
    console.log("Switching playlist:", playlistName);
    socket?.emit("pl_switch", { playlistName });
  };

  const removePlaylist = (playlistName: string) => {
    console.log("Removing playlist:", playlistName);
    socket?.emit("pl_remove_playlist", { playlistName });
  };

  const addSong = (song: string, playlistName?: string) => {
    console.log("Adding song:", song, "to playlist:", playlistName);
    socket?.emit("pl_add", { song, playlistName });
  };

  const removeSong = (artist: string, title: string) => {
    console.log("Removing song:", artist, title);
    socket?.emit("pl_remove", { artist, title });
  };

  const viewPlaylist = (playlistName?: string) => {
    console.log("Viewing playlist:", playlistName);
    socket?.emit("pl_view", { playlistName });
  };

  const viewPlaylists = () => {
    console.log("Viewing all playlists");
    socket?.emit("pl_view_playlists", {});
  };

  const clearPlaylist = (playlistName?: string) => {
    console.log("Clearing playlist:", playlistName);
    socket?.emit("pl_clear", { playlistName });
  };

  const onPlaylistResponse = (callback: (response: any) => void) => {
    if (!socket) return () => {};

    const handler = (data: any) => {
      console.log("Response handler called with:", data);
      callback(data);
    };
    
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

export const usePlaylist = () => {
  const context = useContext(PlaylistContext);
  if (!context) {
    throw new Error("usePlaylist must be used within a PlaylistProvider");
  }
  return context;
};