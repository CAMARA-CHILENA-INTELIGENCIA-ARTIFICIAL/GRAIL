import React from "react";

interface AnimationProps {
  src: string;
  alt: string;
}

export default function Animation({ src, alt }: AnimationProps): React.ReactElement {
  return (
    <figure className="grail-anim">
      <img src={src} alt={alt} loading="lazy" />
    </figure>
  );
}
