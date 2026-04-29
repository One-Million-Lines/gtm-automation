import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { queryClient } from "@/lib/queryClient";
import { ProjectProvider } from "@/state/projectStore";
import { AuthProvider } from "@/state/authStore";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AppShell } from "@/components/layout/AppShell";
import Companies from "@/pages/Companies";
import Contacts from "@/pages/Contacts";
import Dashboard from "@/pages/Dashboard";
import ExperimentDetail from "@/pages/ExperimentDetail";
import Experiments from "@/pages/Experiments";
import ExportDetail from "@/pages/ExportDetail";
import Exports from "@/pages/Exports";
import Feedback from "@/pages/Feedback";
import ICPs from "@/pages/ICPs";
import Leads from "@/pages/Leads";
import Login from "@/pages/Login";
import Outreach from "@/pages/Outreach";
import DecisionTraces from "@/pages/DecisionTraces";
import LeadInbox from "@/pages/LeadInbox";
import PipelineDashboard from "@/pages/PipelineDashboard";
import PipelineRuns from "@/pages/PipelineRuns";
import Quality from "@/pages/Quality";
import Register from "@/pages/Register";
import Replies from "@/pages/Replies";
import Schedules from "@/pages/Schedules";
import Sends from "@/pages/Sends";
import Suppression from "@/pages/Suppression";
import Templates from "@/pages/Templates";
import Tuning from "@/pages/Tuning";
import {
  EmailDrafts,
  Knowledge,
  Settings,
} from "@/pages/Placeholder";

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <AuthProvider>
            <ProjectProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route
                  element={
                    <ProtectedRoute>
                      <AppShell />
                    </ProtectedRoute>
                  }
                >
                  <Route index element={<Dashboard />} />
                  <Route path="icps" element={<ICPs />} />
                  <Route path="companies" element={<Companies />} />
                  <Route path="contacts" element={<Contacts />} />
                  <Route path="leads" element={<Leads />} />
                  <Route path="outreach" element={<Outreach />} />
                  <Route path="quality" element={<Quality />} />
                  <Route path="sends" element={<Sends />} />
                  <Route path="replies" element={<Replies />} />
                  <Route path="experiments" element={<Experiments />} />
                  <Route path="experiments/:id" element={<ExperimentDetail />} />
                  <Route path="exports" element={<Exports />} />
                  <Route path="exports/:id" element={<ExportDetail />} />
                  <Route path="feedback" element={<Feedback />} />
                  <Route path="tuning" element={<Tuning />} />
                  <Route path="email-drafts" element={<EmailDrafts />} />
                  <Route path="templates" element={<Templates />} />
                  <Route path="schedules" element={<Schedules />} />
                  <Route path="inbox" element={<LeadInbox />} />
                  <Route path="reasoning" element={<DecisionTraces />} />
                  <Route path="pipeline-dashboard" element={<PipelineDashboard />} />
                  <Route path="pipeline-runs" element={<PipelineRuns />} />
                  <Route path="knowledge" element={<Knowledge />} />
                  <Route path="suppression" element={<Suppression />} />
                  <Route path="settings" element={<Settings />} />
                </Route>
              </Routes>
            </ProjectProvider>
          </AuthProvider>
        </BrowserRouter>
        <Toaster richColors position="top-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
