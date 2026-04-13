import ScriptsClient from "./ScriptsClient";

interface IvrRoute {
  id: string;
  key_pressed: string;
  action_type: string;
}

interface IvrNode {
  id: string;
  name: string;
  is_start_node: boolean;
  tts_text?: string;
  routes: IvrRoute[];
}

interface CallScript {
  id: string;
  name: string;
  description?: string;
  script_type: string;
  nodes: IvrNode[];
}

export const dynamic = 'force-dynamic';

async function getScripts(): Promise<CallScript[]> {
  try {
    const res = await fetch(
      (process.env.INTERNAL_API_URL || '/api/v1') + '/call-scripts/',
      { cache: 'no-store' }
    );
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function ScriptsPage() {
  const scripts = await getScripts();
  return <ScriptsClient initialScripts={scripts} />;
}
