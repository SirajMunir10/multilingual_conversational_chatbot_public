'use client'
import dynamic from 'next/dynamic'

// The admin runs only in the browser (sign-in cookie, local theme), like the widget.
const AdminApp = dynamic(() => import('@/admin/AdminApp'), { ssr: false })

export default function AdminPage() {
  return <AdminApp />
}
