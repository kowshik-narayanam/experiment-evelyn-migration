#!/usr/bin/env bash
# normalize_flow.sh <file.flow>: prints the Flow so that two builds of build_flows.sh, or a build and the same Flow
# after the Studio Web designer re-saved it, can be diffed.
# Blanks (new on every build): every UUID (Flow id, entryPointId, process keys inside node types, projectId,
#   resourceKey) and the 9-character binding ids ("b" + 8 characters, referenced from nowhere else in the file).
# Drops (what the designer adds; it re-derives all of it, and `pack` writes the same BPMN with or without it):
#   layout position, size, collapsed;   node uniqueId;
#   node outputs and display.icon, only where they equal the node type's own definition (outputDefinition, display.icon);
#   the "error" handle in handleConfiguration of function/flow definitions (it only draws the Error port when
#     inputs.errorHandlingEnabled is true; the edge and that flag are what make the BPMN error boundary event).
# Treats "function.in-solution" / "flow.in-solution" (designer) as "function" / "flow" (CLI) in definitions[].category.
# Keeps everything else: a changed input, expression, edge, variable, binding or node still shows in the diff.
jq -S '
  . as $f
  | .nodes |= map(. as $n
      | (first($f.definitions[] | select(.nodeType == $n.type and .version == $n.typeVersion)) // {}) as $d
      | del(.uniqueId)
      | if .outputs == $d.outputDefinition then del(.outputs) else . end
      | if .display.icon == $d.display.icon then del(.display.icon) else . end)
  | del(.layout.nodes[]?.position, .layout.nodes[]?.size, .layout.nodes[]?.collapsed)
  | .definitions[].category |= sub("\\.in-solution$"; "")
  | (.definitions[] | select(.nodeType | startswith("uipath.core.")) | .handleConfiguration[].handles)
      |= map(select((.id == "error" and .visible == "{inputs.errorHandlingEnabled}") | not))
' "$1" | sed -E 's/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/UUID/g; s/"id": "b[A-Za-z0-9_-]{8}"/"id": "BINDING"/'
