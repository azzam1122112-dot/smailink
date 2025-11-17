// سامي لينك – سكربت محسن لواجهة الموقع الرئيسية

// ===============================
// الوظائف الرئيسية
// ===============================

document.addEventListener('DOMContentLoaded', function() {
  // تهيئة جميع الوظائف الأساسية
  initCoreFunctions();
  
  // تهيئة الوظائف الخاصة بالصفحات
  initPageSpecificFunctions();
});

function initCoreFunctions() {
  initToastSystem();
  initSmoothScroll();
  initHeaderScroll();
  initScrollReveal();
  initMobileMenu();
  initGlobalAnimations();
}

function initPageSpecificFunctions() {
  // صفحة تفاصيل التقني
  if (document.querySelector('.employee-profile')) {
    initEmployeeProfilePage();
  }
  
  // صفحة قائمة التقنيين
  if (document.querySelector('.employees-grid')) {
    initEmployeesGridPage();
  }
}

// ===============================
// نظام التوست
// ===============================

function initToastSystem() {
  const toastContainer = document.getElementById('toast-container');
  
  // إزالة التوست بعد 5 ثواني
  setTimeout(() => {
    document.querySelectorAll('.toast').forEach(toast => {
      animateToastOut(toast);
    });
  }, 5000);

  // إضافة أحداث الإغلاق
  document.querySelectorAll('.toast-close').forEach(button => {
    button.addEventListener('click', function() {
      const toast = this.closest('.toast');
      animateToastOut(toast);
    });
  });
}

function animateToastOut(toast) {
  toast.style.animation = 'toastSlideOut 0.3s ease-in forwards';
  setTimeout(() => {
    if (toast.parentNode) {
      toast.remove();
    }
  }, 300);
}

// ===============================
// التنقل والتمرير
// ===============================

function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      
      if (targetId.length > 1) {
        const target = document.querySelector(targetId);
        
        if (target) {
          e.preventDefault();
          closeMobileMenu();
          scrollToElement(target);
        }
      }
    });
  });
}

function scrollToElement(element) {
  const headerHeight = document.querySelector('.main-header').offsetHeight;
  const targetPosition = element.getBoundingClientRect().top + window.pageYOffset - headerHeight;
  
  window.scrollTo({
    top: targetPosition,
    behavior: 'smooth'
  });
}

function initHeaderScroll() {
  const header = document.querySelector('.main-header');
  let lastScrollY = window.scrollY;
  
  window.addEventListener('scroll', () => {
    // إضافة/إزالة الظل
    if (window.scrollY > 10) {
      header.classList.add('header-scrolled');
    } else {
      header.classList.remove('header-scrolled');
    }
    
    // إخفاء/إظهار الهيدر
    if (window.scrollY > lastScrollY && window.scrollY > 100) {
      header.style.transform = 'translateY(-100%)';
    } else {
      header.style.transform = 'translateY(0)';
    }
    
    lastScrollY = window.scrollY;
  });
}

// ===============================
// الرسوم المتحركة والتأثيرات
// ===============================

function initScrollReveal() {
  const revealElements = document.querySelectorAll('.scroll-reveal');
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
      }
    });
  }, {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
  });
  
  revealElements.forEach(element => {
    observer.observe(element);
  });
}

function initGlobalAnimations() {
  // تأثيرات للبطاقات
  const cards = document.querySelectorAll('.step-card, .team-card, .employee-card');
  
  cards.forEach((card, index) => {
    card.style.animationDelay = `${index * 0.1}s`;
  });
  
  // تأثيرات للأزرار الرئيسية
  initButtonEffects();
  
  // تأثيرات التحميل
  window.addEventListener('load', () => {
    document.body.classList.add('loaded');
  });
}

function initButtonEffects() {
  const primaryButtons = document.querySelectorAll('.btn-primary');
  
  primaryButtons.forEach(button => {
    button.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-2px) scale(1.02)';
    });
    
    button.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0) scale(1)';
    });
  });
}

// ===============================
// القائمة المتنقلة
// ===============================

function initMobileMenu() {
  const menuToggle = document.querySelector('.menu-toggle');
  const body = document.body;
  
  if (menuToggle) {
    menuToggle.addEventListener('click', toggleMobileMenu);
    
    // إغلاق القائمة عند النقر على رابط
    document.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', closeMobileMenu);
    });
  }
}

function toggleMobileMenu() {
  document.body.classList.toggle('nav-open');
}

function closeMobileMenu() {
  document.body.classList.remove('nav-open');
}

// ===============================
// وظائف مساعدة عامة
// ===============================

function showToast(message, type = 'success') {
  const toastContainer = document.getElementById('toast-container') || createToastContainer();
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <div class="toast-message">${message}</div>
    <button class="toast-close">✕</button>
  `;
  
  toastContainer.appendChild(toast);
  
  // إضافة حدث الإغلاق
  toast.querySelector('.toast-close').addEventListener('click', () => {
    animateToastOut(toast);
  });
  
  // إزالة تلقائية بعد 5 ثواني
  setTimeout(() => {
    if (toast.parentNode) {
      animateToastOut(toast);
    }
  }, 5000);
}

function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.className = 'toast-container';
  document.body.appendChild(container);
  return container;
}

// ===============================
// وظائف صفحة تفاصيل التقني
// ===============================

function initEmployeeProfilePage() {
  initPortfolioGallery();
  initSkillTags();
  initProfileContactButtons();
  initProfileScrollAnimations();
  initBioSection();
}

function initPortfolioGallery() {
  const portfolioItems = document.querySelectorAll('.portfolio-item');
  
  portfolioItems.forEach(item => {
    item.addEventListener('click', function(e) {
      if (e.target.tagName === 'A') return;
      
      const image = this.querySelector('.portfolio-image img');
      const title = this.querySelector('.portfolio-title')?.textContent || '';
      const description = this.querySelector('.portfolio-description')?.textContent || '';
      
      if (image) {
        openPortfolioModal(image.src, title, description);
      }
    });
  });
}

function openPortfolioModal(imageSrc, title, description) {
  const modal = createModal();
  modal.innerHTML = `
    <div class="modal-content">
      <div class="modal-header">
        <h3>${title}</h3>
        <button class="modal-close">×</button>
      </div>
      <div class="modal-body">
        <img src="${imageSrc}" alt="${title}">
        ${description ? `<p>${description}</p>` : ''}
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  
  // إظهار الـ modal
  setTimeout(() => {
    modal.style.opacity = '1';
    modal.querySelector('.modal-content').style.transform = 'scale(1)';
  }, 10);
  
  // أحداث الإغلاق
  const closeButton = modal.querySelector('.modal-close');
  closeButton.addEventListener('click', () => closeModal(modal));
  
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal(modal);
  });
}

function createModal() {
  const modal = document.createElement('div');
  modal.className = 'portfolio-modal';
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    opacity: 0;
    transition: opacity 0.3s ease;
  `;
  return modal;
}

function closeModal(modal) {
  modal.style.opacity = '0';
  modal.querySelector('.modal-content').style.transform = 'scale(0.9)';
  setTimeout(() => {
    if (modal.parentNode) {
      modal.remove();
    }
  }, 300);
}

function initSkillTags() {
  const skillTags = document.querySelectorAll('.skill-tag, .skill-tag-small');
  
  skillTags.forEach(tag => {
    tag.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-2px) scale(1.05)';
    });
    
    tag.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0) scale(1)';
    });
  });
}

function initProfileContactButtons() {
  const contactButton = document.querySelector('.contact-button');
  const disabledButton = document.querySelector('.contact-disabled');
  
  if (contactButton) {
    contactButton.addEventListener('click', function() {
      animateButtonClick(this);
    });
  }
  
  if (disabledButton) {
    disabledButton.addEventListener('click', function(e) {
      e.preventDefault();
      showToast('التواصل عبر واتساب موقوف مؤقتًا حسب سياسة المنصة', 'info');
    });
  }
}

function initProfileScrollAnimations() {
  const animatedElements = document.querySelectorAll('.profile-section, .portfolio-item, .project-card');
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.opacity = '1';
        entry.target.style.transform = 'translateY(0)';
      }
    });
  }, { threshold: 0.1 });
  
  animatedElements.forEach(element => {
    element.style.opacity = '0';
    element.style.transform = 'translateY(20px)';
    element.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(element);
  });
}

function initBioSection() {
  const bioSection = document.querySelector('.bio-section');
  if (!bioSection) return;
  
  const bioContent = bioSection.querySelector('.bio-content');
  
  if (bioContent.scrollHeight > 120) {
    bioContent.style.maxHeight = '120px';
    bioContent.style.overflow = 'hidden';
    
    const toggleButton = createBioToggleButton();
    bioSection.appendChild(toggleButton);
    
    toggleButton.addEventListener('click', function() {
      toggleBioContent(bioContent, this);
    });
  }
}

function createBioToggleButton() {
  const button = document.createElement('button');
  button.textContent = 'عرض المزيد';
  button.className = 'bio-toggle';
  button.style.cssText = `
    background: none;
    border: none;
    color: var(--primary-600);
    cursor: pointer;
    font-size: 0.875rem;
    margin-top: 0.5rem;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  `;
  button.innerHTML += ' ↓';
  return button;
}

function toggleBioContent(bioContent, button) {
  if (bioContent.style.maxHeight === '120px') {
    bioContent.style.maxHeight = 'none';
    button.textContent = 'عرض أقل';
    button.innerHTML = 'عرض أقل ↑';
  } else {
    bioContent.style.maxHeight = '120px';
    button.textContent = 'عرض المزيد';
    button.innerHTML = 'عرض المزيد ↓';
  }
}

// ===============================
// وظائف صفحة قائمة التقنيين
// ===============================

function initEmployeesGridPage() {
  initEmployeeCards();
  initRatingStars();
  initGridContactButtons();
  initSkillsHoverEffects();
}

function initEmployeeCards() {
  const employeeCards = document.querySelectorAll('.employee-card');
  
  employeeCards.forEach(card => {
    // تأثيرات Hover
    card.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-8px)';
    });
    
    card.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
    });
    
    // النقر على البطاقة
    card.addEventListener('click', function(e) {
      if (e.target.closest('a') || e.target.closest('button')) return;
      
      const profileLink = this.querySelector('.btn-view-profile');
      if (profileLink) {
        window.location.href = profileLink.href;
      }
    });
  });
}

function initRatingStars() {
  const ratingElements = document.querySelectorAll('.employee-rating');
  
  ratingElements.forEach(ratingElement => {
    const ratingValue = parseFloat(ratingElement.querySelector('.rating-value').textContent) || 0;
    const starsContainer = ratingElement.querySelector('.rating-stars');
    
    if (starsContainer) {
      starsContainer.innerHTML = '';
      
      for (let i = 1; i <= 5; i++) {
        const star = document.createElement('span');
        star.className = i <= ratingValue ? 'rating-star filled' : 'rating-star';
        star.innerHTML = '★';
        starsContainer.appendChild(star);
      }
    }
  });
}

function initGridContactButtons() {
  const contactButtons = document.querySelectorAll('.btn-contact');
  
  contactButtons.forEach(button => {
    button.addEventListener('click', function(e) {
      e.stopPropagation();
      animateButtonClick(this);
      // يمكن إضافة منطق التواصل هنا
      console.log('فتح نافذة التواصل للتقني');
    });
  });
}

function initSkillsHoverEffects() {
  const skillTags = document.querySelectorAll('.skill-tag-small');
  
  skillTags.forEach(tag => {
    tag.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-2px) scale(1.05)';
    });
    
    tag.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0) scale(1)';
    });
  });
}

// ===============================
// وظائف مساعدة مشتركة
// ===============================

function animateButtonClick(button) {
  button.style.transform = 'scale(0.95)';
  setTimeout(() => {
    button.style.transform = 'scale(1)';
  }, 150);
}

// ===============================
// إضافة أنماط CSS الديناميكية
// ===============================

const dynamicStyles = document.createElement('style');
dynamicStyles.textContent = `
  @keyframes toastSlideOut {
    from {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
    to {
      opacity: 0;
      transform: translateX(-50%) translateY(-1rem);
    }
  }
  
  .portfolio-modal .modal-content {
    background: white;
    border-radius: 1rem;
    max-width: 90%;
    max-height: 90%;
    overflow: auto;
    transform: scale(0.9);
    transition: transform 0.3s ease;
  }
  
  .portfolio-modal .modal-header {
    padding: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .portfolio-modal .modal-body {
    padding: 1.5rem;
  }
  
  .portfolio-modal .modal-body img {
    width: 100%;
    max-height: 400px;
    object-fit: contain;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
  }
  
  .portfolio-modal .modal-close {
    background: none;
    border: none;
    font-size: 1.5rem;
    cursor: pointer;
    color: #6b7280;
  }
`;

document.head.appendChild(dynamicStyles);