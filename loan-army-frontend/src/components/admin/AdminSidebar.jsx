import { Link, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import {
    LayoutDashboard,
    Mail,
    Users,
    Settings,
    Trophy,
    LogOut,
    Home,
    Shield,
    Megaphone,
    MessageCircle,
    MessageSquarePlus,
    GraduationCap,
    UserPlus
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuthUI } from '@/context/AuthContext'

const sidebarItems = [
    { icon: LayoutDashboard, label: 'Dashboard', href: '/admin/dashboard' },
    { icon: Mail, label: 'Newsletters', href: '/admin/newsletters' },
    { icon: MessageSquarePlus, label: 'Curation', href: '/admin/curation' },
    { icon: GraduationCap, label: 'Academy', href: '/admin/academy' },
    { icon: Users, label: 'Users', href: '/admin/users' },
    { icon: UserPlus, label: 'Manual Players', href: '/admin/manual-players' },
    { icon: Trophy, label: 'Loans', href: '/admin/loans' },
    { icon: Users, label: 'Players', href: '/admin/players' },
    { icon: Shield, label: 'Teams', href: '/admin/teams' },
    { icon: Megaphone, label: 'Sponsors', href: '/admin/sponsors' },
    { icon: MessageCircle, label: 'Reddit', href: '/admin/reddit' },
    { icon: Settings, label: 'Settings', href: '/admin/settings' },
]

export function AdminSidebar({ className, collapsed = false, onNavigate }) {
    const location = useLocation()
    const { logout } = useAuthUI()
    const handleNavigate = () => {
        if (onNavigate) onNavigate()
    }

    return (
        <div
            className={cn(
                "pb-10 min-h-screen bg-white border-r shadow-sm transition-[width] duration-200 ease-in-out flex flex-col",
                collapsed ? "w-16" : "w-64",
                className
            )}
            data-state={collapsed ? 'collapsed' : 'expanded'}
        >
            <div className="space-y-4 py-4 flex-1 flex flex-col">
                <div className={cn("px-3 py-2", collapsed && "px-2")}>
                    <div className={cn(
                        "flex items-center gap-3 px-3 mb-6 transition-opacity",
                        collapsed ? "justify-center" : "justify-start"
                    )}>
                        <div className="h-9 w-9 rounded-lg bg-blue-600 flex items-center justify-center">
                            <Trophy className="h-5 w-5 text-white" />
                        </div>
                        {!collapsed && <h2 className="text-lg font-bold tracking-tight">The Academy Watch</h2>}
                    </div>
                    <div className="space-y-1">
                        {sidebarItems.map((item) => (
                            <Link
                                key={item.href}
                                to={item.href}
                            >
                                <Button
                                    variant={location.pathname === item.href ? "secondary" : "ghost"}
                                    className={cn(
                                        "w-full justify-start gap-3",
                                        collapsed && "justify-center px-2"
                                    )}
                                    aria-current={location.pathname === item.href ? "page" : undefined}
                                    onClick={handleNavigate}
                                >
                                    <item.icon className="h-4 w-4" />
                                    {!collapsed && <span className="truncate">{item.label}</span>}
                                </Button>
                            </Link>
                        ))}
                    </div>
                </div>
                <div className={cn("px-3 py-2 mt-auto", collapsed && "px-2")}>
                    {!collapsed && (
                        <h2 className="mb-2 px-3 text-sm font-semibold tracking-tight text-gray-500">
                            Account
                        </h2>
                    )}
                    <div className="space-y-1">
                        <Link to="/">
                            <Button
                                variant="ghost"
                                className={cn(
                                    "w-full justify-start gap-3",
                                    collapsed && "justify-center px-2"
                                )}
                                onClick={onNavigate}
                            >
                                <Home className="h-4 w-4" />
                                {!collapsed && <span>Public Site</span>}
                            </Button>
                        </Link>
                        <Button
                            variant="ghost"
                            className={cn(
                                "w-full justify-start gap-3 text-red-600 hover:text-red-600 hover:bg-red-50",
                                collapsed && "justify-center px-2"
                            )}
                            onClick={() => {
                                if (onNavigate) onNavigate()
                                logout()
                            }}
                        >
                            <LogOut className="h-4 w-4" />
                            {!collapsed && <span>Logout</span>}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
