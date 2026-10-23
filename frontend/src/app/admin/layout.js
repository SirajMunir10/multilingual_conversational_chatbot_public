// The back office has its own title and is never indexed by search engines.
export const metadata = {
  title: 'XO Admin',
  robots: { index: false, follow: false }
}

export default function AdminLayout({ children }) {
  return children
}
