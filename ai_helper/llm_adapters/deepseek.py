import json
import re
import requests
from django.conf import settings


class DeepSeekAdapter:
    """
    Minimal DeepSeek adapter.
    If API key/base URL are not configured, it returns deterministic fallback drafts
    so the rest of the pipeline can still be tested end-to-end.
    """

    def __init__(self):
        self.api_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
        self.base_url = getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        self.model = getattr(settings, 'DEEPSEEK_MODEL', 'deepseek-chat')
        self.vision_model = getattr(settings, 'DEEPSEEK_VISION_MODEL', '') or self.model

    def brainstorm_reply(self, messages, mode, llm_mode='chat_economy', llm_model=''):
        if not self.api_key:
            return (
                "Terima kasih, saya sudah menangkap kebutuhan Anda. "
                "Kita lanjutkan diskusi requirement dulu (target audiens, tujuan halaman, CTA, tone). "
                "Jika sudah cukup, klik Generate untuk membuat draft terstruktur."
            )

        system_prompt = (
            "You are ArnaSite AI Copilot for business users (non-technical audience). "
            "Your job in chat phase is requirement discovery only.\n"
            "Hard rules:\n"
            "1) DO NOT output HTML, CSS, JS, JSX, code blocks, or implementation code.\n"
            "2) DO NOT output full template/site JSON in chat phase.\n"
            "3) Keep language simple, practical, and non-technical for business users.\n"
            "4) Ask focused follow-up questions to clarify goals and content.\n"
            "5) Keep response short (max 8 bullet points or short paragraphs).\n"
            "6) Mention that structured data will be generated when user clicks Generate.\n"
            "7) If user asks for code, politely redirect to requirements discussion first.\n"
            "Output language: Bahasa Indonesia.\n"
            "For template mode, discussion should map to structured sections/pages/CTA/content needs.\n"
            "For site mode, discussion should map to template-specific content requirements."
        )

        if llm_mode == 'multimodal_vision':
            llm_messages = [{'role': 'system', 'content': system_prompt}] + messages
            reply = self._chat_text(
                llm_messages,
                model_override=llm_model or self.vision_model,
            )
            return self._enforce_brainstorm_guardrail(reply, llm_messages, llm_model or self.vision_model)

        # Economy mode: flatten multimodal content to plain text.
        text_messages = []
        for m in messages:
            content = m.get('content', '')
            if isinstance(content, list):
                parts = []
                for c in content:
                    if c.get('type') == 'text':
                        parts.append(c.get('text', ''))
                    elif c.get('type') == 'image_url':
                        url = (c.get('image_url') or {}).get('url', '')
                        parts.append(f"[image-reference] {url}")
                content = '\n'.join(p for p in parts if p)
            text_messages.append({'role': m.get('role', 'user'), 'content': content})

        llm_messages = [{'role': 'system', 'content': system_prompt}] + text_messages
        reply = self._chat_text(
            llm_messages,
            model_override=llm_model or self.model,
        )
        return self._enforce_brainstorm_guardrail(reply, llm_messages, llm_model or self.model)

    def generate_template_draft(self, context_text):
        if not self.api_key:
            return {
                'name': 'AI Generated Business Template',
                'slug': 'ai-generated-business-template',
                'description': context_text[:500],
                'category': 'business',
                'preview_image_url': 'https://example.com/preview.jpg',
                'pages': [
                    {
                        'title': 'Home',
                        'slug': 'home',
                        'order': 1,
                        'is_home': True,
                        'sections': [
                            {
                                'type': 'hero',
                                'order': 1,
                                'is_active': True,
                                'blocks': [
                                    {
                                        'title': 'Welcome',
                                        'subtitle': 'Your trusted partner',
                                        'description': 'Generated hero copy.',
                                        'image_url': 'https://example.com/hero.jpg',
                                        'order': 1,
                                        'extra': {'cta_text': 'Get Started', 'cta_url': '/contact'},
                                        'items': [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                'extra_conventions': {
                    'hero': {
                        'cta_text': 'string',
                        'cta_url': 'string'
                    }
                },
            }

        prompt = (
            "Generate a valid JSON object for ArnaSite template draft.\n"
            "STRICT RULES:\n"
            "1) Return JSON only.\n"
            "2) Do not include any keys outside this exact top-level set:\n"
            "   name, slug, description, category, preview_image_url, pages, extra_conventions\n"
            "3) Required top-level keys: name, slug, description, category, preview_image_url, pages, extra_conventions\n"
            "4) pages must be array of objects with keys: title, slug, order, is_home, sections\n"
            "5) sections must be array of objects with keys: type, order, is_active, blocks\n"
            "6) blocks must be array of objects with keys: title, subtitle, description, image_url, order, extra, items\n"
            "7) items must be array of objects with keys: title, description, icon, order\n"
            "8) Do not output keys like: theme, footer, language, sections (top-level), title (top-level)\n"
            "9) image_url and preview_image_url must be absolute URL.\n"
            f"Context:\n{context_text}"
        )
        return self._chat_json(prompt, model_override=self.model)

    def repair_template_draft(self, invalid_payload, validation_errors):
        if not self.api_key:
            return {
                'name': 'AI Generated Business Template',
                'slug': 'ai-generated-business-template',
                'description': 'Auto-repaired fallback template draft.',
                'category': 'business',
                'preview_image_url': 'https://example.com/preview.jpg',
                'pages': [
                    {
                        'title': 'Home',
                        'slug': 'home',
                        'order': 1,
                        'is_home': True,
                        'sections': [
                            {
                                'type': 'hero',
                                'order': 1,
                                'is_active': True,
                                'blocks': [
                                    {
                                        'title': 'Welcome',
                                        'subtitle': 'Business subtitle',
                                        'description': 'Business description',
                                        'image_url': 'https://example.com/hero.jpg',
                                        'order': 1,
                                        'extra': {'cta_text': 'Get Started', 'cta_url': '/contact'},
                                        'items': [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
                'extra_conventions': {'hero': {'cta_text': 'string', 'cta_url': 'string'}},
            }

        prompt = (
            "You produced invalid JSON for ArnaSite template schema.\n"
            "Rewrite into STRICT valid JSON only.\n"
            "Allowed top-level keys ONLY:\n"
            "name, slug, description, category, preview_image_url, pages, extra_conventions\n"
            "Never include additional top-level keys.\n"
            f"Validation errors: {validation_errors}\n"
            f"Previous invalid payload: {json.dumps(invalid_payload)[:20000]}"
        )
        return self._chat_json(prompt, model_override=self.model)

    def generate_site_content_draft(self, context_text, template_id):
        if not self.api_key:
            return {
                'template_id': str(template_id),
                'pages': [
                    {
                        'slug': 'home',
                        'title': 'Home',
                        'is_home': True,
                        'is_active': True,
                        'meta_title': 'Home',
                        'meta_description': 'Generated by AI Copilot.',
                        'sections': [
                            {
                                'type': 'hero',
                                'order': 1,
                                'is_active': True,
                                'blocks': [
                                    {
                                        'order': 1,
                                        'title': 'Nusa Prima',
                                        'subtitle': 'Trusted Energy Partner',
                                        'description': 'Generated site content draft.',
                                        'image_url': 'https://example.com/hero-site.jpg',
                                        'extra': {'cta_text': 'Contact Us', 'cta_url': '/contact'},
                                        'items': [],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }

        prompt = (
            'Generate a valid JSON object for ArnaSite website content draft. '
            'Return JSON only with fields required by site-content.schema.json. '
            f'Template ID: {template_id}. Context: {context_text}'
        )
        return self._chat_json(prompt, model_override=self.model)

    def generate_fe_guide(self, template_payload):
        if not self.api_key:
            return {
                'title': f"Frontend Guide - {template_payload.get('name', 'Template')}",
                'summary': 'Implementation guide generated by AI Copilot.',
                'section_catalog': [
                    {
                        'type': 'hero',
                        'purpose': 'Top section for headline and primary CTA.',
                        'required_fields': ['title', 'subtitle', 'description'],
                        'optional_fields': ['image_url', 'extra.cta_text', 'extra.cta_url'],
                    }
                ],
                'component_mapping': [
                    {
                        'section_type': 'hero',
                        'component_name': 'HeroSection',
                        'props_contract': 'props.blocks[0] with title, subtitle, description, image_url, extra',
                    }
                ],
                'example_payload': template_payload,
                'implementation_notes': [
                    'Sort sections by order ascending.',
                    'Render only active sections.',
                    'Use responsive image sizing for hero visuals.',
                ],
                'markdown': '# Frontend Guide\n\nUse section.type mapping to render components.',
            }

        prompt = (
            'Generate a valid JSON object for FE guide. '
            'Return JSON only with fields required by fe-guide.schema.json. '
            f'Template payload: {json.dumps(template_payload)[:12000]}'
        )
        return self._chat_json(prompt, model_override=self.model)

    def repair_fe_guide_draft(self, template_payload, invalid_payload, validation_errors):
        if not self.api_key:
            # Deterministic fallback in local/mock mode.
            return self.build_fe_guide_from_template(template_payload)

        prompt = (
            'Fix this invalid FE guide JSON so it strictly matches fe-guide.schema.json. '
            'Return JSON only, no markdown fences.\n'
            f'Validation errors: {validation_errors}\n'
            f'Template payload (reference): {json.dumps(template_payload)[:10000]}\n'
            f'Invalid FE guide JSON: {json.dumps(invalid_payload)[:10000]}'
        )
        return self._chat_json(prompt, model_override=self.model)

    def build_fe_guide_from_template(self, template_payload):
        """Deterministic FE guide builder from template payload (schema-safe fallback)."""
        pages = template_payload.get('pages', []) or []
        section_types = []
        for page in pages:
            for section in page.get('sections', []) or []:
                s_type = str(section.get('type', '')).strip()
                if s_type and s_type not in section_types:
                    section_types.append(s_type)
        if not section_types:
            section_types = ['hero']

        section_catalog = []
        component_mapping = []
        for s_type in section_types:
            section_catalog.append({
                'type': s_type,
                'purpose': f'Render {s_type} section content for this template.',
                'required_fields': ['title', 'description'],
                'optional_fields': ['subtitle', 'image_url', 'extra', 'items'],
            })
            component_mapping.append({
                'section_type': s_type,
                'component_name': f"{''.join(part.capitalize() for part in s_type.replace('-', '_').split('_'))}Section",
                'props_contract': 'section.blocks[] with title, subtitle, description, image_url, extra, items',
            })

        template_name = template_payload.get('name', 'Template')
        markdown_lines = [
            f"# Frontend Guide - {template_name}",
            "",
            "## Section Mapping",
        ]
        for s_type in section_types:
            markdown_lines.append(f"- `{s_type}` -> `{''.join(part.capitalize() for part in s_type.replace('-', '_').split('_'))}Section`")

        markdown_lines.extend([
            "",
            "## Implementation Notes",
            "- Sort pages/sections/blocks by `order` ascending.",
            "- Render only active entities (`is_active=true`).",
            "- Keep component props resilient to optional fields.",
        ])

        return {
            'title': f"Frontend Guide - {template_name}",
            'summary': 'Deterministic FE guide generated from template structure.',
            'section_catalog': section_catalog,
            'component_mapping': component_mapping,
            'example_payload': template_payload,
            'implementation_notes': [
                'Sort pages, sections, and blocks by order ascending.',
                'Render only active sections and pages.',
                'Map each section.type to corresponding React component.',
            ],
            'markdown': '\n'.join(markdown_lines),
        }

    def _chat_text(self, messages, model_override=''):
        payload = {
            'model': model_override or self.model,
            'messages': messages,
            'temperature': 0.3,
        }
        resp = requests.post(
            f'{self.base_url}/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content']

    def _chat_json(self, prompt, model_override=''):
        content = self._chat_text([
            {'role': 'system', 'content': 'Return JSON only.'},
            {'role': 'user', 'content': prompt},
        ], model_override=model_override)
        return self._parse_json_content(content)

    def _enforce_brainstorm_guardrail(self, reply: str, llm_messages, model_override: str) -> str:
        """
        Safety net for brainstorming phase.
        If model still returns code-like output, request a corrected non-technical response.
        """
        suspicious_patterns = ['```', '<html', '</html', '<style', '</style', '<script', '</script']
        lowered = reply.lower()
        if any(p in lowered for p in suspicious_patterns):
            repair_instruction = (
                "Your previous response violated policy (code/HTML returned). "
                "Rewrite ONLY as requirement discussion in simple Bahasa Indonesia for business users. "
                "No code block, no HTML, no JSON. "
                "Ask 3-5 practical clarifying questions and mention user can click Generate later."
            )
            repaired = self._chat_text(
                llm_messages + [{'role': 'user', 'content': repair_instruction}],
                model_override=model_override,
            )
            return repaired
        return reply

    def _parse_json_content(self, content: str):
        """
        Parse model output into JSON with light recovery:
        1) direct json.loads
        2) remove markdown code fences
        3) extract first JSON object/array block
        """
        raw = (content or '').strip()
        if not raw:
            raise ValueError('Empty model response while JSON was expected.')

        # 1) direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 2) strip ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            candidate = fence_match.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # 3) extract first {...} or [...]
        obj_start = raw.find('{')
        obj_end = raw.rfind('}')
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            candidate = raw[obj_start:obj_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        arr_start = raw.find('[')
        arr_end = raw.rfind(']')
        if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
            candidate = raw[arr_start:arr_end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        raise ValueError('Model did not return valid JSON content.')
