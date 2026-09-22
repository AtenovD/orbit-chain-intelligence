import { useEffect, useState } from "react";
import { Wallet, X } from "lucide-react";
import { CONNECT_WALLET_EVENT, WALLETCONNECT_PROJECT_ID, discoverWallets, signInWithWallet, type WalletOption } from "./wallet";

/** Listens for `openWalletDialog()` from anywhere in the app and renders the wallet picker. */
export function WalletDialog({ language, onConnected }: { language: "ru" | "en"; onConnected: () => void }) {
  const ru = language === "ru";
  const [open, setOpen] = useState(false);
  const [wallets, setWallets] = useState<WalletOption[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const show = () => { setError(""); setOpen(true); };
    window.addEventListener(CONNECT_WALLET_EVENT, show);
    return () => window.removeEventListener(CONNECT_WALLET_EVENT, show);
  }, []);
  useEffect(() => (open ? discoverWallets(setWallets) : undefined), [open]);

  if (!open) return null;
  const options: WalletOption[] = [...wallets];
  if (WALLETCONNECT_PROJECT_ID) options.push({ id: "walletconnect", name: "WalletConnect", kind: "walletconnect" });

  async function choose(option: WalletOption) {
    setBusy(option.id);
    setError("");
    try {
      await signInWithWallet(option);
      onConnected();
    } catch (value) {
      const message = (value as { message?: string; code?: number }).message || "";
      const rejected = (value as { code?: number }).code === 4001 || /reject|denied|cancel/i.test(message);
      setError(rejected ? (ru ? "Подпись отменена. Кошелёк не подключён." : "Signature cancelled. The wallet was not connected.") : message || (ru ? "Не удалось подключить кошелёк." : "Could not connect the wallet."));
      setBusy("");
    }
  }

  return (
    <div className="modalback" onClick={() => !busy && setOpen(false)}>
      <div className="modal walletdialog" role="dialog" aria-modal="true" aria-labelledby="wallet-title" onClick={(event) => event.stopPropagation()}>
        <header>
          <div>
            <p className="eyebrow">{ru ? "КОШЕЛЁК" : "WALLET"}</p>
            <h2 id="wallet-title">{ru ? "Подключите кошелёк" : "Connect your wallet"}</h2>
          </div>
          <button className="iconbtn" onClick={() => setOpen(false)} aria-label={ru ? "Закрыть" : "Close"} disabled={Boolean(busy)}><X /></button>
        </header>
        <p className="walletdialog-note">
          {ru
            ? "Вы подпишете сообщение, чтобы подтвердить владение адресом. Это бесплатно, не отправляет транзакцию и не даёт доступа к средствам. Взамен вы получаете повышенный лимит использования."
            : "You will sign a message to prove you own the address. It is free, sends no transaction and gives no access to your funds. In return you get a higher usage limit."}
        </p>
        <div className="walletdialog-list">
          {options.map((option) => (
            <button key={option.id} className="walletdialog-option" disabled={Boolean(busy)} onClick={() => choose(option)}>
              {option.icon ? <img src={option.icon} alt="" /> : <Wallet />}
              <b>{option.name}</b>
              <span>{busy === option.id ? (ru ? "Подтвердите в кошельке…" : "Confirm in your wallet…") : ""}</span>
            </button>
          ))}
          {!options.length && (
            <p className="walletdialog-empty">
              {ru
                ? "Кошелёк в браузере не найден. Установите MetaMask или другое расширение и обновите страницу."
                : "No browser wallet found. Install MetaMask or another wallet extension and reload the page."}
            </p>
          )}
        </div>
        {error && <p className="walletdialog-error" role="alert">{error}</p>}
      </div>
    </div>
  );
}
