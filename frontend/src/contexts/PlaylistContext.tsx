import React, { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { PlaylistActions, PlaylistItem, PlaylistState } from "../types";

type PlaylistContextType = PlaylistState & PlaylistActions;

const PlaylistContext = createContext<PlaylistContextType | undefined>(undefined);

export const usePlaylist = (): PlaylistContextType => {
  const ctx = useContext(PlaylistContext);
  if (!ctx) throw new Error("usePlaylist must be used within PlaylistProvider");
  return ctx;
};

const makeId = () => Math.random().toString(36).slice(2, 10);

export const PlaylistProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [items, setItems] = useState<PlaylistItem[]>([]);

  const addItem = useCallback((item: Omit<PlaylistItem, "id">) => {
    setItems((prev) => [...prev, { ...item, id: makeId() }]);
  }, []);

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  const reorder = useCallback((fromIndex: number, toIndex: number) => {
    setItems((prev) => {
      const next = prev.slice();
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ items, addItem, removeItem, clear, reorder }),
    [items, addItem, removeItem, clear, reorder]
  );

  return <PlaylistContext.Provider value={value}>{children}</PlaylistContext.Provider>;
};
