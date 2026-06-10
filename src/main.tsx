import React from 'react'
import ReactDOM from 'react-dom/client'
import { HeroUIProvider } from '@heroui/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

async function boot() {
  try {
    const { worker } = await import('./api/handlers')
    await worker.start({ onUnhandledRequest: 'bypass' })
  } catch (e) {
    console.error('MSW failed to start, rendering without mock API:', e)
  }

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <HeroUIProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </HeroUIProvider>
    </React.StrictMode>,
  )
}

boot()
