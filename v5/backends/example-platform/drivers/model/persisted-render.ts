import type { RenderModelPort, RenderOptions } from "../../core/retrieve/render";
import type { ApplicationGrantProjectedTreeInputSnapshot } from "../../core/retrieve/authorization-boundary";
import { sha256CanonicalContent } from "../../core/retrieve/content-digest";
import { validateGroundedRender } from "./http-render";

export function createPersistedRenderModel(input: {
  model: RenderModelPort;
  projected: ApplicationGrantProjectedTreeInputSnapshot;
  options: RenderOptions;
  read: (key: string) => Promise<string | null>;
  publish: (key: string, response: string) => Promise<string>;
}): RenderModelPort {
  return Object.freeze({
    async render(request: Parameters<RenderModelPort["render"]>[0]) {
      const key = sha256CanonicalContent({
        version: "memory-render-response-v1",
        owner: input.projected.owner_account_id,
        projection: input.projected.projected_content_digest,
        authorization: input.projected.projection_authorization_digest,
        reader: input.projected.reader_projection_digest,
        options: input.options,
        request,
      });
      const cached = await input.read(key);
      if (cached !== null) return validateGroundedRender(JSON.parse(cached), request.input);
      const response = validateGroundedRender(await input.model.render(request), request.input);
      const winner = await input.publish(key, JSON.stringify(response));
      return validateGroundedRender(JSON.parse(winner), request.input);
    },
  });
}
