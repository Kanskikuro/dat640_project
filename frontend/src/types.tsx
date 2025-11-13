export type ChatMessageButton = {
  title: string;
  payload: string;
  button_type: string;
};

export type ChatMessageAttachment = {
  type: string;
  payload: {
    images?: string[];
    buttons?: ChatMessageButton[];
  };
};

export type ChatMessage = {
  attachments?: ChatMessageAttachment[];
  text?: string;
  intent?: string;
};

export type AgentMessage = {
  recipient: string;
  message: ChatMessage;
  info?: string;
};

export type UserMessage = {
  message: string;
};

// Playlist types
export type PlaylistContextType = {
  switchPlaylist: (playlistName: string) => void;
  createPlaylist: (playlistName: string) => void;
  removePlaylist: (playlistName: string) => void;
  viewPlaylist: (playlistName?: string) => void;
  viewPlaylists: () => void;
  clearPlaylist: (playlistName?: string) => void;

  addSong: (song: string, playlistName?: string) => void;
  removeSong: (artist: string, title: string) => void;

  onPlaylistResponse: (callback: (response: any) => void) => () => void;
};
