import { BarChart3 } from "lucide-react";

export default function AnalyticsPage() {
  return (
    <div className="p-8 pb-20 sm:p-12 w-full max-w-6xl mx-auto relative z-10">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white mb-1">Analytics Engine</h1>
          <p className="text-muted-foreground">Historical metrics and Live Transfer conversions.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="col-span-full p-12 text-center bg-background/60 backdrop-blur-xl border border-white/10 rounded-2xl">
          <BarChart3 className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
          <h3 className="text-xl font-medium text-white mb-2 tracking-tight">Insufficient Data</h3>
          <p className="text-muted-foreground max-w-md mx-auto">Complete at least one highly-concurrent outbound campaign to visualize answer rates, AMD accuracy, and agent conversion funnels.</p>
        </div>
      </div>
    </div>
  );
}
