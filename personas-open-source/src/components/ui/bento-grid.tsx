import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { BarChart2, Clock } from 'lucide-react'

const topics = [
  { name: "AI Cloning", mentions: 183, color: "bg-blue-500" },
  { name: "Memory", mentions: 122, color: "bg-pink-500" },
  { name: "Voice AI", mentions: 321, color: "bg-purple-500" },
  { name: "Privacy", mentions: 223, color: "bg-indigo-500" },
  { name: "Intelligence", mentions: 321, color: "bg-orange-500" },
  { name: "Companionship", mentions: 564, color: "bg-cyan-500" },
  { name: "Future Tech", mentions: 133, color: "bg-emerald-500" },
]

const activeUsers = Array(10).fill(null).map((_, i) => ({
  image: `/placeholder.svg?height=32&width=32&text=${i + 1}`,
  name: `Pioneer ${i + 1}`,
}))

export function BentoGrid() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Popular Topics */}
        <Card className="p-6 bg-white/5 backdrop-blur-sm border-0">
          <h3 className="font-light mb-4 text-white">Popular Topics</h3>
          <div className="flex flex-wrap gap-2">
            {topics.map((topic) => (
              <Badge
                key={topic.name}
                variant="secondary"
                className="rounded-full py-1 px-3 bg-white/5 hover:bg-white/10"
              >
                <span className={`w-2 h-2 rounded-full ${topic.color} mr-2 inline-block`} />
                {topic.name}
                <span className="text-xs ml-2 text-gray-400">{topic.mentions}</span>
              </Badge>
            ))}
          </div>
        </Card>

        {/* Most Active Users */}
        <Card className="p-6 bg-white/5 backdrop-blur-sm border-0">
          <h3 className="font-light mb-4 text-white">Early Pioneers</h3>
          <div className="flex flex-wrap gap-2">
            {activeUsers.map((user, i) => (
              <Avatar key={i} className="w-8 h-8 border-2 border-blue-500/20">
                <AvatarImage src={user.image} alt={user.name} />
                <AvatarFallback>{user.name[0]}</AvatarFallback>
              </Avatar>
            ))}
          </div>
          <div className="mt-4 text-sm text-gray-400">
            <span className="font-medium text-blue-400">@FirstPioneer</span>
            <span className="ml-2">76 interactions</span>
          </div>
        </Card>

        {/* Most Asked Questions */}
        <Card className="p-6 bg-white/5 backdrop-blur-sm border-0">
          <h3 className="font-light mb-4 text-white">Popular Questions</h3>
          <div className="bg-blue-500/10 text-white rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <BarChart2 className="h-4 w-4 text-blue-400" />
              <span className="text-sm text-blue-400">Most Asked · 163x</span>
            </div>
            <p className="font-light">How does Omi learn from me?</p>
          </div>
        </Card>

        {/* Recent Questions */}
        <Card className="p-6 bg-white/5 backdrop-blur-sm border-0">
          <h3 className="font-light mb-4 text-white">Recent Questions</h3>
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <Clock className="h-4 w-4 text-blue-400 mt-1" />
              <div>
                <div className="flex items-center gap-2 text-sm text-gray-400">
                  <span>New</span>
                  <span>24x</span>
                </div>
                <p className="text-sm text-white">Can Omi help me be more productive?</p>
              </div>
            </div>
          </div>
        </Card>

        {/* Conversation Alert */}
        <Card className="p-6 md:col-span-2 lg:col-span-2 bg-white/5 backdrop-blur-sm border-0">
          <h3 className="font-light mb-4 text-white">Latest Conversation</h3>
          <div className="flex items-start gap-3">
            <span className="w-2 h-2 rounded-full bg-blue-500 mt-2" />
            <div>
              <div className="font-light mb-1 text-white">AI Companion Update</div>
              <p className="text-sm text-gray-400">
                Experience the next evolution of AI companionship with our latest update...
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
} 