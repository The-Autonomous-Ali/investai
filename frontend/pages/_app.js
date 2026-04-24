import { SessionProvider } from 'next-auth/react'
import '../styles/globals.css'
import BetaBanner from '../components/BetaBanner'

export default function App({ Component, pageProps: { session, ...pageProps } }) {
  return (
    <SessionProvider session={session}>
      <BetaBanner />
      <Component {...pageProps} />
    </SessionProvider>
  )
}
