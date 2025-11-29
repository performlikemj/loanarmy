
import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import { Menu, PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { AdminSidebar } from '@/components/admin/AdminSidebar'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useAuth } from '@/context/AuthContext'

const SIDEBAR_COLLAPSE_KEY = 'loan_army_admin_sidebar_collapsed'

export function AdminLayout() {
    const { token, isAdmin, hasApiKey } = useAuth()
    const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
    const [collapsed, setCollapsed] = useState(() => {
        if (typeof localStorage === 'undefined') return false
        return localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === 'true'
    })

    useEffect(() => {
        if (typeof localStorage === 'undefined') return
        localStorage.setItem(SIDEBAR_COLLAPSE_KEY, collapsed ? 'true' : 'false')
    }, [collapsed])

    useEffect(() => {
        const closeOnResize = () => {
            if (window.innerWidth >= 1024) {
                setMobileSidebarOpen(false)
            }
        }
        window.addEventListener('resize', closeOnResize)
        return () => window.removeEventListener('resize', closeOnResize)
    }, [])

    if (!token || !isAdmin || !hasApiKey) {
        return <Navigate to="/" replace />
    }

    return (
        <div className="flex min-h-screen bg-gray-50">
            <AdminSidebar
                collapsed={collapsed}
                className="hidden lg:flex"
            />

            <Sheet open={mobileSidebarOpen} onOpenChange={setMobileSidebarOpen}>
                <SheetContent
                    side="left"
                    className="p-0 w-72 sm:w-80 lg:hidden"
                    data-testid="admin-sidebar-sheet"
                >
                    <SheetHeader className="sr-only">
                        <SheetTitle>Admin menu</SheetTitle>
                    </SheetHeader>
                    <AdminSidebar onNavigate={() => setMobileSidebarOpen(false)} />
                </SheetContent>
            </Sheet>

            <div className="flex-1 min-w-0">
                <header className="sticky top-0 z-20 h-16 border-b bg-white/90 backdrop-blur flex items-center px-4 sm:px-6 justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0">
                        <Button
                            data-testid="admin-menu-toggle"
                            className="md:hidden"
                            variant="ghost"
                            size="icon"
                            aria-label="Open admin menu"
                            onClick={() => setMobileSidebarOpen(true)}
                        >
                            <Menu className="h-5 w-5" />
                        </Button>
                        <Button
                            data-testid="admin-collapse-toggle"
                            className="hidden lg:inline-flex"
                            variant="ghost"
                            size="icon"
                            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                            onClick={() => setCollapsed((prev) => !prev)}
                        >
                            {collapsed ? <PanelLeftOpen className="h-5 w-5" /> : <PanelLeftClose className="h-5 w-5" />}
                        </Button>
                        <div className="min-w-0">
                            <h1 className="text-lg sm:text-xl font-semibold text-gray-900 truncate">Admin Dashboard</h1>
                            <p className="text-xs text-gray-500 hidden sm:block">Control center for journalists, loans, and newsletters</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-gray-600">
                        <span className="hidden sm:inline">Logged in as Admin</span>
                    </div>
                </header>
                <main className="p-4 sm:p-6">
                    <Outlet />
                </main>
            </div>
        </div>
    )
}
