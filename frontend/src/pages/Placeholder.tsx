import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function Placeholder({ title, file }: { title: string; file: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-muted-foreground text-sm">
        Coming soon — {file}
      </CardContent>
    </Card>
  );
}

export const Leads = () => <Placeholder title="Leads" file="File 12" />;
export const EmailDrafts = () => <Placeholder title="Email Drafts" file="File 15" />;
export const Knowledge = () => <Placeholder title="Knowledge Base" file="File 13" />;
export const Settings = () => <Placeholder title="Settings" file="later" />;
