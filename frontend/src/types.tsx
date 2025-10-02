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
export type PlaylistItem = {
  id: string; // stable id for drag/drop
  artist: string;
  title: string;
  album?: string;
  durationMs?: number;
  spotifyUri?: string;
};

export type PlaylistState = {
  items: PlaylistItem[];
};

export type PlaylistActions = {
  addItem: (item: Omit<PlaylistItem, "id">) => void;
  removeItem: (id: string) => void;
  clear: () => void;
  reorder: (fromIndex: number, toIndex: number) => void;
};
