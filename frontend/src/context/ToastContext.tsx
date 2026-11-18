import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

interface Toast {
  id: string;
  type: "success" | "error" | "info";
  message: string;
}

interface ToastContextType {
  toast: {
    success: (msg: string) => void;
    error: (msg: string) => void;
    info: (msg: string) => void;
  };
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const add = useCallback((type: "success" | "error" | "info", message: string) => {
    const id = Math.random().toString(36).slice(2);
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4500);
  }, []);

  const remove = (id: string) => setToasts(prev => prev.filter(t => t.id !== id));

  const toast = {
    success: (msg: string) => add("success", msg),
    error: (msg: string) => add("error", msg),
    info: (msg: string) => add("info", msg),
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
        {toasts.map(t => (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 rounded-lg border p-3.5 shadow-xl text-sm transition-all duration-200 ${
              t.type === "success"
                ? "border-green-500/30 bg-green-950/90 text-green-200"
                : t.type === "error"
                ? "border-red-500/30 bg-red-950/90 text-red-200"
                : "border-blue-500/30 bg-zinc-900/90 text-zinc-200"
            }`}
          >
            {t.type === "success" && <CheckCircle2 className="w-5 h-5 text-green-400 shrink-0" />}
            {t.type === "error" && <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />}
            {t.type === "info" && <Info className="w-5 h-5 text-blue-400 shrink-0" />}
            <span className="flex-1 break-words">{t.message}</span>
            <button onClick={() => remove(t.id)} className="text-zinc-400 hover:text-white shrink-0">
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return {
    toast: ctx.toast,
    addToast: (type: "success" | "error" | "info", msg: string) => ctx.toast[type](msg),
    ...ctx.toast,
  };
}
