import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Les appels /api sont transmis à Django (port 8000).
// Port 3000 sur 127.0.0.1 : sous Windows, le port 5173 est parfois réservé par le système.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // Administration Django (création des comptes) depuis la même adresse que l'application.
      "/admin": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
    },
  },
});
