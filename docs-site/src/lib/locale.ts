import useDocusaurusContext from "@docusaurus/useDocusaurusContext";

export function useCurrentLocale(): string {
  const { i18n } = useDocusaurusContext();
  return i18n.currentLocale ?? "es";
}
