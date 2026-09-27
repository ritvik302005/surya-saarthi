import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // keep /*! licence and credit comments (e.g. the MIT notice in wave-background.jsx) in the built files
  build: { rolldownOptions: { output: { comments: { legal: true } } } },
})