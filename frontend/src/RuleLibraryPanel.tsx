import { useEffect, useState } from "react";

type RuleTemplate = {
  id: string; name: string; category: string; description: string; pattern: string;
  mapping_prefix: string; priority: number; example_before: string; example_after: string; notes: string;
  match_type: "regex"; replacement: string; replacement_mode: "indexed";
  case_sensitive: boolean; enabled: boolean; profile_id: null;
};
type Category = { name: string; description: string; template_count: number };

async function requestLibrary() {
  const response = await fetch("/api/rules/library", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Die Vorlagenbibliothek konnte nicht geladen werden.");
  return await response.json() as { categories: Category[]; templates: RuleTemplate[] };
}

export function RuleLibraryPanel({ onAddTemplate }: { onAddTemplate: (template: RuleTemplate) => void }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [templates, setTemplates] = useState<RuleTemplate[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("Alle Kategorien");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    void requestLibrary().then(data => {
      if (!active) return;
      setCategories(data.categories);
      setTemplates(data.templates);
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : "Ladefehler.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const visible = selectedCategory === "Alle Kategorien"
    ? templates
    : templates.filter(template => template.category === selectedCategory);

  if (loading) return <div className="rule-library"><p role="status">Regelvorlagen werden geladen …</p></div>;
  if (error) return <div className="rule-library"><p className="error-message" role="alert">{error}</p></div>;

  return <div className="rule-library">
    <div className="rule-library-heading">
      <div><h3>Vorkonfigurierte Regelbibliothek</h3><p>Wähle passende Vorlagen aus und passe sie anschließend im Regeleditor an deine Logquellen an.</p></div>
      <label>Kategorie<select value={selectedCategory} onChange={event => setSelectedCategory(event.target.value)}>
        <option>Alle Kategorien</option>{categories.map(category => <option key={category.name} value={category.name}>{category.name} ({category.template_count})</option>)}
      </select></label>
    </div>
    <p className="rule-library-safety"><strong>Wichtig:</strong> Vorlagen werden zunächst deaktiviert hinzugefügt. Prüfe Muster und Beispiele mit deinen Logformaten und aktiviere nur passende Regeln. Die Bibliothek ist ein Startpunkt und keine vollständige Geheimniserkennung.</p>
    <div className="rule-template-grid">
      {visible.map(template => <article className="rule-template-card" key={template.id}>
        <div className="rule-template-title"><div><h4>{template.name}</h4><span className="rule-template-category">{template.category}</span></div><span className="rule-template-priority">Priorität {template.priority}</span></div>
        <p>{template.description}</p>
        <label>Regex-Muster<code className="rule-template-pattern">{template.pattern}</code></label>
        <div className="rule-template-example"><span>Beispiel</span><code>{template.example_before}</code><span>Erwartete Form</span><code>{template.example_after}</code></div>
        <p className="rule-template-note">{template.notes}</p>
        <button className="secondary-button" type="button" onClick={() => onAddTemplate(template)}>Vorlage übernehmen</button>
      </article>)}
    </div>
    {visible.length === 0 && <p className="muted-message">Für diese Kategorie sind keine Vorlagen vorhanden.</p>}
  </div>;
}
