import { Waveform } from "../components/TimeSeries";
import { FAULT_CARDS } from "./content";

// Map the project's own fault vocabulary onto waveform shapes.
const SHAPE: Record<string, string> = {
  spike: "spike", drift: "drift", stuck: "stuck", step: "bias",
  noise: "noise", dropout: "stuck", physics: "spike", storm: "noise",
};

export function FaultLibrary() {
  return (
    <>
      <div className="eyebrow">What breaking looks like</div>
      <h1 className="display" style={{ fontSize: 40 }}>Fault Library</h1>
      <p className="lede">
        Each fault leaves a distinct signature in the trace. Recognise the shape and you can name the
        cause — which is what an engineer actually needs to hear. These are the classes SkyGuard's
        fault simulator injects and evaluates.
      </p>

      <div className="faults">
        {FAULT_CARDS.map((f) => (
          <article className="fcard" key={f.k}>
            <div className="wave"><Waveform kind={SHAPE[f.k] ?? "noise"} /></div>
            <div className="bd">
              <h3>{f.n}</h3>
              <p>{f.d}</p>
              <div className="sig">{f.c}</div>
            </div>
          </article>
        ))}
      </div>

      <div className="note accent" style={{ marginTop: 26 }}>
        Detection performance for these classes was measured under <b>controlled synthetic fault
        injection</b> across eight NOAA ISD stations. No field-labelled sensor failure has been
        scored, so these are simulation results, not real-world accuracy.
      </div>
    </>
  );
}
