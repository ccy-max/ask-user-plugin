/**
 * Type declarations for the QwenPaw Console host SDK.
 *
 * This file provides type hints for ``window.QwenPaw.*`` when
 * developing frontend plugins.  The actual APIs are available at
 * runtime provided by the Console.
 */

declare namespace QwenPaw {
  namespace host {
    const React: any;
    const ReactDOM: any;
    const antd: any;
    const antdIcons: any;
    const apiBaseUrl: string;

    function getApiUrl(path: string): string;
    function getApiToken(): string | null;
    function getSelectedAgentId(): string;
    function getCurrentSessionId(): string;

    function useTheme(): string;
    function useLocale(): string;
    function useSelectedAgent(): { id: string };
    function useCurrentSession(): { id: string } | null;
    function fetch(url: string, init?: any): Promise<Response>;
  }

  namespace menu {
    function add(pluginId: string, item: any | any[]): { dispose(): void };
    function replace(pluginId: string, targetId: string, item: any): { dispose(): void };
    function remove(targetId: string): void;
  }

  namespace route {
    function add(pluginId: string, route: any | any[]): { dispose(): void };
    function replace(pluginId: string, targetId: string, component: any): { dispose(): void };
    function wrap(pluginId: string, targetId: string, wrapper: any): { dispose(): void };
    function remove(targetId: string): void;
  }

  namespace slot {
    function fill(pluginId: string, name: string, render: any, opts?: any): { dispose(): void };
    function replace(pluginId: string, name: string, render: any, opts?: any): { dispose(): void };
  }

  namespace chat {
    namespace welcome {
      function set(pluginId: string, config: any): { dispose(): void };
      function render(pluginId: string, component: any): { dispose(): void };
    }

    namespace leftHeader {
      function set(pluginId: string, config: any): { dispose(): void };
    }

    namespace rightHeader {
      function add(pluginId: string, element: any, opts?: any): { dispose(): void };
    }

    namespace sender {
      function set(pluginId: string, config: any): { dispose(): void };
      function addSuggestion(pluginId: string, config: any): { dispose(): void };
    }

    namespace request {
      function prepend(pluginId: string, render: any, opts?: any): { dispose(): void };
      function render(pluginId: string, component: any, opts?: any): { dispose(): void };
    }

    namespace response {
      function append(pluginId: string, render: any, opts?: any): { dispose(): void };
      function render(pluginId: string, component: any, opts?: any): { dispose(): void };
    }

    namespace toolRender {
      (pluginId: string, toolName: string, component: any): { dispose(): void };
    }

    namespace actions {
      function add(pluginId: string, config: any): { dispose(): void };
    }

    namespace requestActions {
      function add(pluginId: string, config: any): { dispose(): void };
    }

    function disposeAll(pluginId: string): void;
  }

  namespace audit {
    function overrides(): any[];
  }
}

interface Window {
  QwenPaw: typeof QwenPaw;
}
