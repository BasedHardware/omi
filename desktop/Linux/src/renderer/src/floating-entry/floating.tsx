import React from 'react'
import { createRoot } from 'react-dom/client'
import '../theme.css'
import { FloatingBar } from './FloatingBar'

document.body.style.background = 'transparent'

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <FloatingBar />
  </React.StrictMode>
)
